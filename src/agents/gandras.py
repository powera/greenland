#!/usr/bin/env python3
"""
Gandras - Audio Manifest Downloader Agent

This agent scans S3 staging directories for manifest files, matches them against
the database, and downloads audio files for matching entries.

"Gandras" means "stork" in Lithuanian - a migratory bird that brings things home.

Matching Strategy:
- REQUIRED: language_code and expected_text must match exactly
- RECOMMENDED: guid (for lemmas) or sentence_id (for sentences) should match
- OPTIONAL: part of speech can be verified via the lemma's pos_type field
"""

import argparse
import hashlib
import json
import logging
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

# Add src directory to path
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

import constants
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_processing_args,
    get_data_source_config,
)
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import (
    AudioQualityReview,
    Lemma,
    Sentence,
    SentenceTranslation,
)
from storage.translation_helpers import get_translation

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ManifestEntry:
    """Parsed manifest entry from S3."""

    md5: str
    agent: str
    voice_name: str
    language_code: str
    expected_text: str
    guid: Optional[str]
    sentence_id: Optional[int]
    grammatical_form: Optional[str]
    generated_at: str
    file_size_bytes: int
    generation_params: Optional[Dict[str, Any]]
    s3_audio_key: str
    s3_manifest_key: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any], audio_key: str, manifest_key: str) -> "ManifestEntry":
        """Create ManifestEntry from manifest dict."""
        return cls(
            md5=data.get("md5", ""),
            agent=data.get("agent", ""),
            voice_name=data.get("voice_name", ""),
            language_code=data.get("language_code", ""),
            expected_text=data.get("expected_text", ""),
            guid=data.get("guid"),
            sentence_id=data.get("sentence_id"),
            grammatical_form=data.get("grammatical_form"),
            generated_at=data.get("generated_at", ""),
            file_size_bytes=data.get("file_size_bytes", 0),
            generation_params=data.get("generation_params"),
            s3_audio_key=audio_key,
            s3_manifest_key=manifest_key,
        )


@dataclass
class MatchResult:
    """Result of matching a manifest to database records."""

    matched: bool
    match_type: str  # "guid", "sentence_id", "text_only", "no_match"
    lemma: Optional[Lemma]
    sentence: Optional[Sentence]
    text_matches: bool
    guid_matches: bool
    sentence_id_matches: bool
    pos_type: Optional[str]
    warnings: List[str]


class GandrasAgent:
    """Agent for downloading audio manifests from S3 staging."""

    def __init__(
        self,
        config: DataSourceConfig,
        output_dir: Optional[str] = None,
        require_guid_match: bool = True,
        require_text_match: bool = True,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize the Gandras agent.

        Args:
            config: DataSourceConfig with database settings
            output_dir: Output directory for downloaded audio (uses temp dir if None)
            require_guid_match: Require GUID/sentence_id match (default: True)
            require_text_match: Require text match (default: True)
            dry_run: If True, only report what would be downloaded without downloading
        """
        self.config = config
        self.debug = config.debug
        self.require_guid_match = require_guid_match
        self.require_text_match = require_text_match
        self.dry_run = dry_run
        self.output_dir = (
            Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="gandras_"))
        )

        if self.debug:
            logger.setLevel(logging.DEBUG)

        # Lazy-initialize S3 client
        self._s3_uploader: Optional[Any] = None

        # Ensure output directory exists
        if not self.dry_run:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {self.output_dir}")

    @property
    def s3_uploader(self) -> Any:
        """Lazy-initialize S3 uploader."""
        if self._s3_uploader is None:
            from clients.audio.s3_uploader import S3AudioUploader

            self._s3_uploader = S3AudioUploader()
        return self._s3_uploader

    def get_session(self) -> Session:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def list_staging_manifests(
        self,
        language_code: Optional[str] = None,
        voice_name: Optional[str] = None,
        agent_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Tuple[str, str]]:
        """
        List manifest files in S3 staging directory.

        Args:
            language_code: Filter by language code
            voice_name: Filter by voice name
            agent_filter: Filter by agent name in path (for legacy staging/{agent}/ structure)
            limit: Maximum number of manifests to return

        Returns:
            List of (audio_key, manifest_key) tuples
        """
        # Build prefix based on filters
        # New structure: staging/{language}/{voice}/{md5}.manifest
        # Legacy structure: staging/{agent}/{md5}.manifest
        prefix = "staging/"

        if language_code and voice_name:
            prefix = f"staging/{language_code}/{voice_name}/"
        elif language_code:
            prefix = f"staging/{language_code}/"
        elif agent_filter:
            prefix = f"staging/{agent_filter}/"

        logger.info(f"Listing manifests with prefix: {prefix}")

        manifests: List[Tuple[str, str]] = []
        paginator = self.s3_uploader.s3.get_paginator("list_objects_v2")

        try:
            for page in paginator.paginate(Bucket=self.s3_uploader.bucket_name, Prefix=prefix):
                if "Contents" not in page:
                    continue

                for obj in page["Contents"]:
                    key = obj["Key"]
                    if key.endswith(".manifest"):
                        # Derive audio key from manifest key
                        audio_key = key.replace(".manifest", ".mp3")
                        manifests.append((audio_key, key))

                        if limit and len(manifests) >= limit:
                            return manifests

        except Exception as e:
            logger.error(f"Error listing S3 objects: {e}")
            raise

        logger.info(f"Found {len(manifests)} manifest files")
        return manifests

    def download_manifest(self, manifest_key: str) -> Optional[Dict[str, Any]]:
        """
        Download and parse a manifest file from S3.

        Args:
            manifest_key: S3 key for manifest file

        Returns:
            Parsed manifest dict or None on error
        """
        try:
            response = self.s3_uploader.s3.get_object(
                Bucket=self.s3_uploader.bucket_name, Key=manifest_key
            )
            content = response["Body"].read().decode("utf-8")
            result: Dict[str, Any] = json.loads(content)
            return result
        except Exception as e:
            logger.error(f"Error downloading manifest {manifest_key}: {e}")
            return None

    def match_manifest_to_database(self, session: Session, manifest: ManifestEntry) -> MatchResult:
        """
        Match a manifest entry against the database.

        Matching priority:
        1. If guid is present, try to match lemma by GUID
        2. If sentence_id is present, try to match sentence by ID
        3. Fall back to text matching within the language

        Args:
            session: Database session
            manifest: Parsed manifest entry

        Returns:
            MatchResult with match details
        """
        warnings: List[str] = []
        lemma: Optional[Lemma] = None
        sentence: Optional[Sentence] = None
        text_matches = False
        guid_matches = False
        sentence_id_matches = False
        pos_type: Optional[str] = None

        # Try GUID match for lemmas
        if manifest.guid and not manifest.guid.startswith("S_"):
            lemma = session.query(Lemma).filter_by(guid=manifest.guid).first()

            if lemma:
                guid_matches = True
                pos_type = lemma.pos_type

                # Check if text matches translation
                db_translation = get_translation(session, lemma, manifest.language_code)
                if db_translation:
                    # Normalize for comparison (strip whitespace, lowercase for comparison)
                    manifest_text_norm = manifest.expected_text.strip().lower()
                    db_text_norm = db_translation.strip().lower()
                    text_matches = manifest_text_norm == db_text_norm

                    if not text_matches:
                        warnings.append(
                            f"Text mismatch: manifest='{manifest.expected_text}' "
                            f"vs db='{db_translation}'"
                        )
                else:
                    warnings.append(
                        f"No {manifest.language_code} translation found for lemma {manifest.guid}"
                    )

        # Try sentence_id match
        if manifest.sentence_id:
            sentence = session.query(Sentence).filter_by(id=manifest.sentence_id).first()

            if sentence:
                sentence_id_matches = True

                # Check if text matches translation
                translation = (
                    session.query(SentenceTranslation)
                    .filter_by(
                        sentence_id=manifest.sentence_id, language_code=manifest.language_code
                    )
                    .first()
                )

                if translation:
                    manifest_text_norm = manifest.expected_text.strip().lower()
                    db_text_norm = translation.translation_text.strip().lower()
                    text_matches = manifest_text_norm == db_text_norm

                    if not text_matches:
                        warnings.append(
                            f"Text mismatch: manifest='{manifest.expected_text}' "
                            f"vs db='{translation.translation_text}'"
                        )
                else:
                    warnings.append(
                        f"No {manifest.language_code} translation found for sentence {manifest.sentence_id}"
                    )

        # Determine match type and whether it's a valid match
        if guid_matches and text_matches:
            match_type = "guid"
            matched = True
        elif sentence_id_matches and text_matches:
            match_type = "sentence_id"
            matched = True
        elif guid_matches and not text_matches:
            match_type = "guid_text_mismatch"
            matched = not self.require_text_match  # Match if text match not required
        elif sentence_id_matches and not text_matches:
            match_type = "sentence_id_text_mismatch"
            matched = not self.require_text_match
        elif not manifest.guid and not manifest.sentence_id:
            match_type = "no_identifier"
            matched = False
            warnings.append("Manifest has no guid or sentence_id")
        else:
            match_type = "no_match"
            matched = False
            if manifest.guid:
                warnings.append(f"GUID {manifest.guid} not found in database")
            if manifest.sentence_id:
                warnings.append(f"Sentence ID {manifest.sentence_id} not found in database")

        return MatchResult(
            matched=matched,
            match_type=match_type,
            lemma=lemma,
            sentence=sentence,
            text_matches=text_matches,
            guid_matches=guid_matches,
            sentence_id_matches=sentence_id_matches,
            pos_type=pos_type,
            warnings=warnings,
        )

    def download_audio_file(self, audio_key: str, output_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Download audio file from S3.

        Args:
            audio_key: S3 key for audio file
            output_path: Local path to save file

        Returns:
            Tuple of (success, md5_hash)
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would download {audio_key} to {output_path}")
            return True, None

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.s3_uploader.s3.download_file(
                self.s3_uploader.bucket_name, audio_key, str(output_path)
            )

            # Calculate MD5 to verify
            md5_hash = hashlib.md5(output_path.read_bytes()).hexdigest()
            logger.info(f"Downloaded {audio_key} to {output_path} (MD5: {md5_hash})")
            return True, md5_hash
        except Exception as e:
            logger.error(f"Error downloading {audio_key}: {e}")
            return False, None

    def create_or_update_review_record(
        self,
        session: Session,
        manifest: ManifestEntry,
        match_result: MatchResult,
        local_filename: str,
    ) -> Optional[AudioQualityReview]:
        """
        Create or update an AudioQualityReview record.

        Args:
            session: Database session
            manifest: Manifest entry
            match_result: Match result with lemma/sentence info
            local_filename: Local filename for the audio

        Returns:
            Created or updated AudioQualityReview record
        """
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would create/update AudioQualityReview for "
                f"{manifest.guid or f'sentence_{manifest.sentence_id}'}"
            )
            return None

        # Build S3 URLs
        audio_url = self.s3_uploader.get_cdn_url(manifest.s3_audio_key)
        manifest_url = self.s3_uploader.get_cdn_url(manifest.s3_manifest_key)

        # Check for existing record
        existing: Optional[AudioQualityReview] = None
        if manifest.guid and match_result.lemma:
            existing = (
                session.query(AudioQualityReview)
                .filter_by(
                    guid=manifest.guid,
                    language_code=manifest.language_code,
                    voice_name=manifest.voice_name,
                    grammatical_form=manifest.grammatical_form,
                )
                .first()
            )
        elif manifest.sentence_id and match_result.sentence:
            existing = (
                session.query(AudioQualityReview)
                .filter_by(
                    sentence_id=manifest.sentence_id,
                    language_code=manifest.language_code,
                    voice_name=manifest.voice_name,
                )
                .first()
            )

        if existing:
            # Update existing record
            existing.filename = local_filename
            existing.expected_text = manifest.expected_text
            existing.manifest_md5 = manifest.md5
            existing.s3_staging_url = audio_url
            existing.s3_staging_manifest_url = manifest_url
            existing.staging_agent = manifest.agent
            # Reset to pending_review since we're re-downloading
            existing.status = "pending_review"
            existing.reviewed_at = None
            logger.debug(
                f"Updated existing review record for "
                f"{manifest.guid or f'sentence_{manifest.sentence_id}'}"
            )
            return existing

        # Create new record
        review = AudioQualityReview(
            guid=manifest.guid,
            sentence_id=manifest.sentence_id,
            language_code=manifest.language_code,
            voice_name=manifest.voice_name,
            grammatical_form=manifest.grammatical_form,
            filename=local_filename,
            expected_text=manifest.expected_text,
            manifest_md5=manifest.md5,
            s3_staging_url=audio_url,
            s3_staging_manifest_url=manifest_url,
            s3_prod_url=None,
            staging_agent=manifest.agent,
            lemma_id=match_result.lemma.id if match_result.lemma else None,
            status="pending_review",
        )
        session.add(review)
        logger.debug(
            f"Created review record for {manifest.guid or f'sentence_{manifest.sentence_id}'}"
        )
        return review

    def process_manifests(
        self,
        language_code: Optional[str] = None,
        voice_name: Optional[str] = None,
        agent_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process manifests from S3 staging.

        Args:
            language_code: Filter by language code
            voice_name: Filter by voice name
            agent_filter: Filter by agent name
            limit: Maximum number of manifests to process

        Returns:
            Dict with processing results
        """
        results: Dict[str, Any] = {
            "total_manifests": 0,
            "matched": 0,
            "downloaded": 0,
            "skipped": 0,
            "errors": 0,
            "match_types": {},
            "warnings": [],
            "entries": [],
        }

        # List manifests
        manifest_keys = self.list_staging_manifests(
            language_code=language_code,
            voice_name=voice_name,
            agent_filter=agent_filter,
            limit=limit,
        )
        results["total_manifests"] = len(manifest_keys)

        if not manifest_keys:
            logger.info("No manifests found")
            return results

        session = self.get_session()
        try:
            for i, (audio_key, manifest_key) in enumerate(manifest_keys, 1):
                logger.info(f"[{i}/{len(manifest_keys)}] Processing {manifest_key}")

                # Download and parse manifest
                manifest_data = self.download_manifest(manifest_key)
                if not manifest_data:
                    results["errors"] += 1
                    results["warnings"].append(f"Failed to download manifest: {manifest_key}")
                    continue

                # Create manifest entry
                manifest = ManifestEntry.from_dict(manifest_data, audio_key, manifest_key)

                # Apply filters if manifest doesn't include them in path
                if language_code and manifest.language_code != language_code:
                    logger.debug(f"Skipping {manifest_key}: language mismatch")
                    results["skipped"] += 1
                    continue

                if voice_name and manifest.voice_name != voice_name:
                    logger.debug(f"Skipping {manifest_key}: voice mismatch")
                    results["skipped"] += 1
                    continue

                # Match against database
                match_result = self.match_manifest_to_database(session, manifest)

                # Track match type
                match_type = match_result.match_type
                results["match_types"][match_type] = results["match_types"].get(match_type, 0) + 1

                entry_result: Dict[str, Any] = {
                    "manifest_key": manifest_key,
                    "guid": manifest.guid,
                    "sentence_id": manifest.sentence_id,
                    "language_code": manifest.language_code,
                    "voice_name": manifest.voice_name,
                    "expected_text": (
                        manifest.expected_text[:50] + "..."
                        if len(manifest.expected_text) > 50
                        else manifest.expected_text
                    ),
                    "match_type": match_type,
                    "matched": match_result.matched,
                    "pos_type": match_result.pos_type,
                    "warnings": match_result.warnings,
                }

                if match_result.matched:
                    results["matched"] += 1

                    # Download audio file
                    identifier = manifest.guid or f"sent_{manifest.sentence_id}"
                    safe_text = manifest.expected_text.lower().replace(" ", "_")[:30]
                    local_filename = f"{identifier}_{safe_text}.mp3"

                    output_path = (
                        self.output_dir
                        / manifest.language_code
                        / manifest.voice_name
                        / local_filename
                    )

                    success, downloaded_md5 = self.download_audio_file(audio_key, output_path)

                    if success:
                        # Verify MD5 if we downloaded
                        if downloaded_md5 and downloaded_md5 != manifest.md5:
                            logger.warning(
                                f"MD5 mismatch for {audio_key}: "
                                f"manifest={manifest.md5}, downloaded={downloaded_md5}"
                            )
                            match_result.warnings.append("MD5 mismatch after download")

                        # Create/update review record
                        self.create_or_update_review_record(
                            session, manifest, match_result, local_filename
                        )
                        results["downloaded"] += 1
                        entry_result["downloaded"] = True
                        entry_result["local_path"] = str(output_path)
                    else:
                        results["errors"] += 1
                        entry_result["downloaded"] = False
                        entry_result["error"] = "Download failed"
                else:
                    results["skipped"] += 1
                    entry_result["downloaded"] = False
                    results["warnings"].extend(match_result.warnings)

                results["entries"].append(entry_result)

            # Commit all changes
            if not self.dry_run:
                session.commit()

        finally:
            session.close()

        return results


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Gandras - Audio Manifest Downloader Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Matching Strategy:
  By default, both GUID/sentence_id AND text must match.

  Use --no-require-guid to allow downloads even when GUID/sentence_id
  doesn't match (matches by text only within the language).

  Use --no-require-text to allow downloads even when the text doesn't
  exactly match (matches by GUID/sentence_id only).

Examples:
  # List all manifests in staging
  %(prog)s --mode list

  # Download manifests for Lithuanian/ruta voice
  %(prog)s --language lt --voice ruta

  # Download with relaxed matching (GUID match only)
  %(prog)s --language lt --no-require-text

  # Dry run to see what would be downloaded
  %(prog)s --language lt --dry-run
""",
    )

    # Common arguments
    add_common_args(parser)
    add_processing_args(parser)
    add_backend_args(parser)

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["list", "download", "report"],
        default="download",
        help="Operation mode: list (show manifests), download (download matching audio), "
        "report (show match statistics without downloading)",
    )

    # Filter options
    parser.add_argument(
        "--language",
        help="Filter by language code (e.g., lt, zh, es)",
    )
    parser.add_argument(
        "--voice",
        help="Filter by voice name (e.g., ruta, jonas, meiling)",
    )
    parser.add_argument(
        "--agent",
        help="Filter by agent name in S3 path (for legacy staging/{agent}/ structure)",
    )

    # Output options
    parser.add_argument(
        "--output-dir",
        help="Output directory for downloaded audio (default: temp directory)",
    )

    # Matching options
    parser.add_argument(
        "--no-require-guid",
        action="store_true",
        help="Don't require GUID/sentence_id match (allow text-only matching)",
    )
    parser.add_argument(
        "--no-require-text",
        action="store_true",
        help="Don't require text match (allow GUID-only matching)",
    )

    return parser


def main() -> None:
    """Main entry point for the gandras agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args
    config = get_data_source_config(args)

    # Create agent
    agent = GandrasAgent(
        config=config,
        output_dir=args.output_dir,
        require_guid_match=not args.no_require_guid,
        require_text_match=not args.no_require_text,
        dry_run=args.dry_run,
    )

    # Handle modes
    if args.mode == "list":
        # List manifests in S3
        print("\nListing manifests in S3 staging...")
        print("=" * 80)

        manifests = agent.list_staging_manifests(
            language_code=args.language,
            voice_name=args.voice,
            agent_filter=args.agent,
            limit=args.limit,
        )

        for audio_key, manifest_key in manifests:
            print(f"  {manifest_key}")

        print(f"\nTotal: {len(manifests)} manifests")
        return

    elif args.mode == "report":
        # Report on manifest matching without downloading
        print("\nManifest Match Report")
        print("=" * 80)

        # Use dry_run mode for report
        agent.dry_run = True
        results = agent.process_manifests(
            language_code=args.language,
            voice_name=args.voice,
            agent_filter=args.agent,
            limit=args.limit,
        )

        print(f"\nTotal manifests: {results['total_manifests']}")
        print(f"Matched: {results['matched']}")
        print(f"Skipped (no match): {results['skipped']}")
        print(f"Errors: {results['errors']}")

        print("\nMatch types:")
        for match_type, count in sorted(results["match_types"].items()):
            print(f"  {match_type}: {count}")

        if results["warnings"]:
            print(f"\nWarnings ({len(results['warnings'])}):")
            for warning in results["warnings"][:10]:
                print(f"  - {warning}")
            if len(results["warnings"]) > 10:
                print(f"  ... and {len(results['warnings']) - 10} more")

        return

    elif args.mode == "download":
        # Download matching audio
        print("\nDownloading audio from S3 staging...")
        print("=" * 80)

        if args.dry_run:
            print("[DRY RUN MODE - no files will be downloaded]")

        results = agent.process_manifests(
            language_code=args.language,
            voice_name=args.voice,
            agent_filter=args.agent,
            limit=args.limit,
        )

        # Print summary
        print("\n" + "=" * 80)
        print("GANDRAS AGENT REPORT - Audio Manifest Download")
        print("=" * 80)
        print(f"Total manifests: {results['total_manifests']}")
        print(f"Matched: {results['matched']}")
        print(f"Downloaded: {results['downloaded']}")
        print(f"Skipped: {results['skipped']}")
        print(f"Errors: {results['errors']}")
        print(f"Output directory: {agent.output_dir}")

        print("\nMatch types:")
        for match_type, count in sorted(results["match_types"].items()):
            print(f"  {match_type}: {count}")

        if results["warnings"]:
            print(f"\nWarnings ({len(results['warnings'])}):")
            for warning in results["warnings"][:10]:
                print(f"  - {warning}")
            if len(results["warnings"]) > 10:
                print(f"  ... and {len(results['warnings']) - 10} more")

        # Print first few entries with details
        if args.debug and results["entries"]:
            print("\nSample entries:")
            for entry in results["entries"][:5]:
                print(
                    f"  {entry['guid'] or entry['sentence_id']} "
                    f"[{entry['language_code']}/{entry['voice_name']}] "
                    f"- {entry['match_type']}"
                )
                if entry.get("pos_type"):
                    print(f"    POS: {entry['pos_type']}")
                if entry.get("warnings"):
                    for w in entry["warnings"]:
                        print(f"    WARNING: {w}")

        print("=" * 80)


if __name__ == "__main__":
    main()
