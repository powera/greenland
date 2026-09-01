#!/usr/bin/env python3
"""
Gandras - Audio Manifest Import Agent

This agent scans S3 staging directories for manifest files, matches them against
the database, and writes an AudioQualityReview row for each match.

The import is metadata-only by default. Everything a review row holds - the
MD5, the staging URLs, the expected text, the agent - comes from the manifest
JSON, and the MP3s themselves are served to clients straight from S3, so there
is no reason to transfer the audio to import it. Pass --fetch-audio when a
local copy is genuinely wanted (spot-checking a voice, say); it also verifies
each file's MD5 against its manifest.

"Gandras" means "stork" in Lithuanian - a migratory bird that brings things home.

Matching Strategy:
- REQUIRED: language_code and expected_text must match exactly
- RECOMMENDED: guid (for lemmas) or sentence_id (for sentences) should match
- OPTIONAL: part of speech can be verified via the lemma's pos_type field
"""

import argparse
import logging
import sys
import tempfile
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
from audiotools import s3_ops
from audiotools.review_records import clear_review_verdict, find_existing_review
from audiotools.staging_manifest import (
    ManifestEntry,
    MatchResult,
    match_manifest_to_database,
)
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.models.schema import AudioQualityReview

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class GandrasAgent:
    """Agent for downloading audio manifests from S3 staging."""

    def __init__(
        self,
        config: DataSourceConfig,
        output_dir: Optional[str] = None,
        require_guid_match: bool = True,
        require_text_match: bool = True,
        dry_run: bool = False,
        fetch_audio: bool = False,
        import_rejected: bool = False,
    ) -> None:
        """
        Initialize the Gandras agent.

        Args:
            config: DataSourceConfig with database settings
            output_dir: Output directory for downloaded audio (uses temp dir if None)
            require_guid_match: Require GUID/sentence_id match (default: True)
            require_text_match: Require text match (default: True)
            dry_run: If True, only report what would be downloaded without downloading
            fetch_audio: If True, also download each matched MP3. Off by default:
                the review row is built entirely from the manifest JSON, and the
                MP3s are served from S3, so importing metadata needs no transfer
                of the audio itself.
            import_rejected: If True, import audio whose manifest is marked
                rejected in S3. Off by default -- a rejection travels with the
                manifest precisely so every database honors it.
        """
        self.config = config
        self.debug = config.debug
        self.require_guid_match = require_guid_match
        self.require_text_match = require_text_match
        self.dry_run = dry_run
        self.fetch_audio = fetch_audio
        self.import_rejected = import_rejected
        # A temp dir is only made when MP3s are actually fetched, so a
        # metadata-only run leaves nothing behind.
        self.output_dir: Optional[Path]
        if output_dir:
            self.output_dir = Path(output_dir)
        elif fetch_audio:
            self.output_dir = Path(tempfile.mkdtemp(prefix="gandras_"))
        else:
            self.output_dir = None

        if self.debug:
            logger.setLevel(logging.DEBUG)

        # Lazy-initialize S3 client
        self._s3_uploader: Optional[Any] = None

        # Ensure output directory exists (only meaningful when fetching MP3s)
        if self.fetch_audio and not self.dry_run and self.output_dir is not None:
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
        return s3_ops.list_staging_manifests(
            uploader=self.s3_uploader,
            language_code=language_code,
            voice_name=voice_name,
            agent_filter=agent_filter,
            limit=limit,
        )

    def download_manifest(self, manifest_key: str) -> Optional[Dict[str, Any]]:
        """
        Download and parse a manifest file from S3.

        Args:
            manifest_key: S3 key for manifest file

        Returns:
            Parsed manifest dict or None on error
        """
        return s3_ops.download_manifest(self.s3_uploader, manifest_key)

    def match_manifest_to_database(self, session: Session, manifest: ManifestEntry) -> MatchResult:
        """
        Match a manifest entry against the database.

        Thin wrapper over audiotools.staging_manifest.match_manifest_to_database,
        supplying this agent's require_text_match setting.

        Args:
            session: Database session
            manifest: Parsed manifest entry

        Returns:
            MatchResult with match details
        """
        return match_manifest_to_database(
            session, manifest, require_text_match=self.require_text_match
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

        return s3_ops.download_audio_file(self.s3_uploader, audio_key, output_path)

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
            logger.info(f"[DRY RUN] Would create/update AudioQualityReview for {manifest.label}")
            return None

        # Build S3 URLs
        audio_url = self.s3_uploader.get_cdn_url(manifest.s3_audio_key)
        manifest_url = self.s3_uploader.get_cdn_url(manifest.s3_manifest_key)

        # Check for existing record
        existing: Optional[AudioQualityReview] = None
        if manifest.guid and match_result.lemma:
            existing = find_existing_review(
                session,
                language_code=manifest.language_code,
                voice_name=manifest.voice_name,
                guid=manifest.guid,
                grammatical_form=manifest.grammatical_form,
            )
        elif manifest.sentence_id and match_result.sentence:
            existing = find_existing_review(
                session,
                language_code=manifest.language_code,
                voice_name=manifest.voice_name,
                sentence_id=manifest.sentence_id,
            )

        if existing:
            # Second line of defence against resurrecting rejected audio. The
            # first is the manifest's own "rejected" block, which process_manifests
            # honors before reaching here and which every database sees; this
            # local check still covers audio rejected in this database before the
            # verdict was pushed to S3 (see s3_ops.mark_manifest_rejected).
            # Same MD5 means the same file, since staging keys are the audio MD5.
            if existing.status == "needs_replacement" and existing.manifest_md5 == manifest.md5:
                logger.info(
                    f"Skipping re-import of rejected audio for {manifest.label} "
                    f"(status=needs_replacement, same MD5)"
                )
                return existing

            # Update existing record
            existing.filename = local_filename
            existing.expected_text = manifest.expected_text
            existing.manifest_md5 = manifest.md5
            existing.s3_staging_url = audio_url
            existing.s3_staging_manifest_url = manifest_url
            existing.staging_agent = manifest.agent
            # Reset to pending_review since we're re-downloading
            existing.status = "pending_review"
            clear_review_verdict(existing)
            logger.debug(f"Updated existing review record for {manifest.label}")
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
        logger.debug(f"Created review record for {manifest.label}")
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
            "imported": 0,
            "rejected": 0,
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

                # The manifest itself says this audio was rejected, so no
                # database needs to have made that call locally to honor it.
                if manifest.is_rejected and not self.import_rejected:
                    logger.info(
                        f"Skipping rejected audio for {manifest.label}: "
                        f"{manifest.rejection_reason}"
                    )
                    results["rejected"] += 1
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

                    identifier = manifest.guid or f"sent_{manifest.sentence_id}"
                    safe_text = manifest.expected_text.lower().replace(" ", "_")[:30]
                    local_filename = f"{identifier}_{safe_text}.mp3"

                    # The review row is built from the manifest alone, so the
                    # MP3 is fetched only when explicitly asked for.
                    if self.fetch_audio:
                        assert self.output_dir is not None  # set whenever fetch_audio
                        output_path = (
                            self.output_dir
                            / manifest.language_code
                            / manifest.voice_name
                            / local_filename
                        )

                        success, downloaded_md5 = self.download_audio_file(audio_key, output_path)

                        if not success:
                            results["errors"] += 1
                            entry_result["downloaded"] = False
                            entry_result["error"] = "Download failed"
                            results["entries"].append(entry_result)
                            continue

                        # Verify MD5 if we downloaded
                        if downloaded_md5 and downloaded_md5 != manifest.md5:
                            logger.warning(
                                f"MD5 mismatch for {audio_key}: "
                                f"manifest={manifest.md5}, downloaded={downloaded_md5}"
                            )
                            match_result.warnings.append("MD5 mismatch after download")

                        entry_result["local_path"] = str(output_path)

                    # Create/update review record
                    self.create_or_update_review_record(
                        session, manifest, match_result, local_filename
                    )
                    results["imported"] += 1
                    entry_result["imported"] = True
                    entry_result["downloaded"] = self.fetch_audio
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
        description="Gandras - Audio Manifest Import Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Matching Strategy:
  By default, both GUID/sentence_id AND text must match.

  Use --no-require-guid to allow imports even when GUID/sentence_id
  doesn't match (matches by text only within the language).

  Use --no-require-text to allow imports even when the text doesn't
  exactly match (matches by GUID/sentence_id only).

Examples:
  # List all manifests in staging
  %(prog)s --mode list

  # Import audio metadata for Lithuanian/ruta voice (no MP3 transfer)
  %(prog)s --language lt --voice ruta

  # Import with relaxed matching (GUID match only)
  %(prog)s --language lt --no-require-text

  # Dry run to see what would be imported
  %(prog)s --language lt --dry-run

  # Also pull down the MP3s themselves
  %(prog)s --language lt --fetch-audio --output-dir /tmp/lt_audio
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
        help="Operation mode: list (show manifests), download (import matching "
        "manifests into the database), report (show match statistics without writing)",
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
        help="Output directory for downloaded audio (default: temp directory). "
        "Only used with --fetch-audio.",
    )

    parser.add_argument(
        "--import-rejected",
        action="store_true",
        help="Import audio even when its manifest is marked rejected in S3. "
        "Off by default, so a rejection recorded by any database is honored here.",
    )

    parser.add_argument(
        "--fetch-audio",
        action="store_true",
        help="Also download each matched MP3. Off by default: the review record "
        "is built from the manifest JSON and the MP3s are served from S3, so a "
        "metadata import needs no audio transfer.",
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
        fetch_audio=args.fetch_audio,
        import_rejected=args.import_rejected,
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
        print(f"Rejected in S3: {results['rejected']}")
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
        if args.fetch_audio:
            print("\nImporting audio metadata from S3 staging (with MP3 download)...")
        else:
            print("\nImporting audio metadata from S3 staging...")
        print("=" * 80)

        if args.dry_run:
            print("[DRY RUN MODE - no records will be written]")

        results = agent.process_manifests(
            language_code=args.language,
            voice_name=args.voice,
            agent_filter=args.agent,
            limit=args.limit,
        )

        # Print summary
        print("\n" + "=" * 80)
        print("GANDRAS AGENT REPORT - Audio Manifest Import")
        print("=" * 80)
        print(f"Total manifests: {results['total_manifests']}")
        print(f"Matched: {results['matched']}")
        print(f"Imported: {results['imported']}")
        print(f"Rejected in S3: {results['rejected']}")
        print(f"Skipped: {results['skipped']}")
        print(f"Errors: {results['errors']}")
        if args.fetch_audio:
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
