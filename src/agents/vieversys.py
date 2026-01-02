#!/usr/bin/env python3
"""
Vieversys - Audio Generation Agent

This agent generates audio files for lemmas using OpenAI TTS API.
Files are generated to a temporary directory, stored with metadata in the
AudioQualityReview table with 'pending_review' status, and can later be
uploaded to S3 after review.

"Vieversys" means "lark" in Lithuanian - a bird known for its beautiful song.
"""

import argparse
import hashlib
import json
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from agents.common.common_args import (
    add_common_args,
    add_processing_args,
    add_backend_args,
    add_guid_arg,
    add_llm_args,
    confirm_operation,
    get_data_source_config,
)
from agents.common.lemma_selection import find_lemma_by_guid, LemmaQueryBuilder, apply_limit_and_sample_rate
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig, BackendType
from wordfreq.storage.models.schema import Lemma, AudioQualityReview
from wordfreq.storage.translation_helpers import get_translation
from clients.audio import generate_audio, Voice, AudioFormat

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Default voices for each language (3 per language as specified)
DEFAULT_VOICES = {
    "lt": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "zh": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "ko": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "fr": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "de": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "es": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "pt": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "sw": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
    "vi": [Voice.ASH, Voice.ALLOY, Voice.NOVA],
}


class VieversysAgent:
    """Agent for generating audio files for lemmas."""

    def __init__(
        self,
        config: DataSourceConfig,
        output_dir: str = None,
    ):
        """
        Initialize the Vieversys agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            output_dir: Output directory for generated audio (uses temp dir if None)
        """
        self.config = config
        self.debug = config.debug
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="vieversys_"))

        if self.debug:
            logger.setLevel(logging.DEBUG)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {self.output_dir}")

    def get_session(self):
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_translation_text(self, session, lemma: Lemma, language_code: str) -> Optional[str]:
        """
        Get translation text for a lemma in a specific language.

        Args:
            session: Database session
            lemma: Lemma object
            language_code: Language code (e.g., "lt", "zh")

        Returns:
            Translation text or None if not available
        """
        return get_translation(session, lemma, language_code)

    def generate_audio_for_lemma(
        self,
        session,
        lemma: Lemma,
        language_code: str,
        voices: List[Voice],
        create_review_record: bool = True,
    ) -> Dict:
        """
        Generate audio files for a lemma in a specific language with multiple voices.

        Args:
            session: Database session
            lemma: Lemma to generate audio for
            language_code: Target language code
            voices: List of voices to use
            create_review_record: Whether to create AudioQualityReview records

        Returns:
            Dict with generation results
        """
        # Get translation text
        text = self.get_translation_text(session, lemma, language_code)
        if not text:
            logger.warning(f"No {language_code} translation for lemma {lemma.guid}")
            return {
                "success": False,
                "lemma_guid": lemma.guid,
                "language": language_code,
                "error": "No translation available",
            }

        results = {
            "success": True,
            "lemma_guid": lemma.guid,
            "language": language_code,
            "text": text,
            "voices": [],
        }

        for voice in voices:
            logger.info(f"Generating audio: {text} ({language_code}/{voice.value})")

            # Generate audio
            result = generate_audio(text=text, voice=voice, language_code=language_code)

            if not result.success:
                logger.error(f"Failed to generate audio: {result.error}")
                results["voices"].append(
                    {
                        "voice": voice.value,
                        "success": False,
                        "error": result.error,
                    }
                )
                continue

            # Create filename and save
            # Use sanitized text for filename (simple version - just lowercase and replace spaces)
            safe_text = text.lower().replace(" ", "_")[:50]  # Limit length
            filename = f"{lemma.guid}_{safe_text}.mp3"

            # Create language/voice subdirectories
            voice_dir = self.output_dir / language_code / voice.value
            voice_dir.mkdir(parents=True, exist_ok=True)

            file_path = voice_dir / filename

            # Write audio data
            file_path.write_bytes(result.audio_data)

            # Calculate MD5
            md5_hash = hashlib.md5(result.audio_data).hexdigest()

            logger.info(f"Saved audio: {file_path} (MD5: {md5_hash})")

            # Create review record if requested
            if create_review_record:
                self._create_review_record(
                    session, lemma, language_code, voice.value, filename, text, md5_hash
                )

            results["voices"].append(
                {
                    "voice": voice.value,
                    "success": True,
                    "filename": filename,
                    "file_path": str(file_path),
                    "md5": md5_hash,
                    "duration_ms": result.duration_ms,
                }
            )

        return results

    def _create_review_record(
        self,
        session,
        lemma: Lemma,
        language_code: str,
        voice_name: str,
        filename: str,
        text: str,
        md5_hash: str,
    ):
        """Create AudioQualityReview record for generated audio."""
        # Check if record already exists
        existing = (
            session.query(AudioQualityReview)
            .filter_by(
                guid=lemma.guid,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=None,  # Base form
            )
            .first()
        )

        if existing:
            # Update existing record
            existing.filename = filename
            existing.expected_text = text
            existing.manifest_md5 = md5_hash
            existing.status = "pending_review"
            existing.s3_url = None  # Will be set after upload
            logger.debug(f"Updated existing review record for {lemma.guid}")
        else:
            # Create new record
            review = AudioQualityReview(
                guid=lemma.guid,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=None,  # Base form
                filename=filename,
                expected_text=text,
                manifest_md5=md5_hash,
                s3_url=None,  # Will be set after S3 upload
                lemma_id=lemma.id,
                status="pending_review",
            )
            session.add(review)
            logger.debug(f"Created review record for {lemma.guid}")

        session.commit()

    def generate_batch(
        self,
        language_code: str,
        limit: Optional[int] = None,
        difficulty_level: Optional[int] = None,
        voices: Optional[List[Voice]] = None,
    ) -> Dict:
        """
        Generate audio for a batch of lemmas.

        Args:
            language_code: Target language code
            limit: Maximum number of lemmas to process
            difficulty_level: Filter by difficulty level
            voices: Voices to use (defaults to language's default voices)

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()
        voices = voices or DEFAULT_VOICES.get(language_code, [Voice.ASH, Voice.ALLOY, Voice.NOVA])

        try:
            # Build query
            builder = LemmaQueryBuilder(session).curated_only().order_by_id()

            # Filter by difficulty level if specified
            if difficulty_level is not None:
                builder = builder.by_difficulty_level(difficulty_level)

            query = builder.build()

            # Filter lemmas that have translation in target language
            # Note: We'll filter in Python after fetching since get_translation handles both column and table-based lookups
            # This is simpler and avoids needing to know which languages use which storage method

            # Apply limit
            if limit:
                query = query.limit(limit)

            all_lemmas = query.all()

            # Filter to only lemmas that have translations in the target language
            lemmas = []
            for lemma in all_lemmas:
                if self.get_translation_text(session, lemma, language_code):
                    lemmas.append(lemma)

            logger.info(f"Generating audio for {len(lemmas)} lemmas in {language_code}")

            results = {
                "language_code": language_code,
                "total_lemmas": len(lemmas),
                "voices": [v.value for v in voices],
                "output_dir": str(self.output_dir),
                "lemmas": [],
                "success_count": 0,
                "error_count": 0,
            }

            for i, lemma in enumerate(lemmas, 1):
                logger.info(f"[{i}/{len(lemmas)}] Processing {lemma.guid}")

                result = self.generate_audio_for_lemma(
                    session, lemma, language_code, voices, create_review_record=True
                )

                results["lemmas"].append(result)
                if result["success"]:
                    results["success_count"] += 1
                else:
                    results["error_count"] += 1

            return results

        finally:
            session.close()

    def generate_manifest(self, language_code: str, voice_name: str) -> Path:
        """
        Generate audio_manifest.json for a specific language/voice combination.

        Args:
            language_code: Language code
            voice_name: Voice name

        Returns:
            Path to generated manifest file
        """
        voice_dir = self.output_dir / language_code / voice_name
        if not voice_dir.exists():
            raise ValueError(f"Voice directory not found: {voice_dir}")

        manifest = {"language": language_code, "voice": voice_name, "files": {}}

        # Scan for MP3 files
        for mp3_file in voice_dir.glob("*.mp3"):
            # Calculate MD5
            md5_hash = hashlib.md5(mp3_file.read_bytes()).hexdigest()

            # Extract GUID from filename (format: {GUID}_{text}.mp3)
            filename_parts = mp3_file.stem.split("_", 1)
            guid = filename_parts[0] if len(filename_parts) > 0 else "UNKNOWN"

            # Get text from filename (not ideal but works for now)
            text = filename_parts[1] if len(filename_parts) > 1 else guid

            manifest["files"][mp3_file.name] = {
                "guid": guid,
                "text": text,
                "md5": md5_hash,
                "grammatical_form": None,
            }

        # Write manifest
        manifest_path = voice_dir / "audio_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

        logger.info(f"Generated manifest: {manifest_path} ({len(manifest['files'])} files)")
        return manifest_path


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Vieversys - Audio Generation Agent")

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_backend_args(parser)

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["check-existing", "populate-only", "regenerate", "coverage"],
        default="coverage",
        help="Operation mode: check-existing (list existing audio), populate-only (generate missing only), regenerate (delete and regenerate), coverage (report only, default)",
    )

    # Vieversys-specific arguments
    parser.add_argument("--output-dir", help="Output directory for generated audio")
    parser.add_argument(
        "--language",
        choices=["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi"],
        help="Target language code (required for populate-only and regenerate modes)",
    )
    parser.add_argument(
        "--difficulty-level", type=int, help="Filter by difficulty level (1-20)"
    )
    parser.add_argument(
        "--voices",
        nargs="+",
        choices=["ash", "alloy", "nova", "ballad", "coral", "echo", "fable", "onyx", "sage", "shimmer"],
        help="Voices to use (defaults to ash, alloy, nova)",
    )
    parser.add_argument(
        "--generate-manifests",
        action="store_true",
        help="Generate audio_manifest.json files after generation",
    )

    return parser


def main():
    """Main entry point for the vieversys agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Validate mode-specific requirements
    if args.mode in ["populate-only", "regenerate"] and not args.language:
        print(f"Error: --language is required for --mode {args.mode}")
        sys.exit(1)

    # Create agent with config
    agent = VieversysAgent(
        config=config,
        output_dir=args.output_dir,
    )

    # Convert voice names to Voice enums
    voices = None
    if args.voices:
        voices = [Voice(v) for v in args.voices]

    # Handle --guid mode (single lemma)
    if args.guid:
        session = agent.get_session()
        try:
            lemma = find_lemma_by_guid(session, args.guid)

            print(f"\nProcessing audio for: {lemma.lemma_text} (GUID: {args.guid})")
            print(f"POS: {lemma.pos_type}")

            # For single lemma, require language
            if not args.language:
                print("Error: --language is required when using --guid")
                sys.exit(1)

            # Check if translation exists
            translation = agent.get_translation_text(session, lemma, args.language)
            if not translation:
                print(f"Error: No {args.language} translation found for this lemma")
                sys.exit(1)

            print(f"Translation ({args.language}): {translation}")

            # Use default voices if not specified
            voice_list = voices or DEFAULT_VOICES.get(args.language, [Voice.ASH, Voice.ALLOY, Voice.NOVA])

            print(f"\nGenerating audio with voices: {', '.join(v.value for v in voice_list)}")

            # Generate audio for the single lemma
            result = agent.generate_audio_for_lemma(
                session, lemma, args.language, voice_list, create_review_record=True
            )

            if result["success"]:
                print(f"\n✓ Successfully generated audio for {len(result['voices'])} voice(s)")
                for voice_result in result['voices']:
                    if voice_result['success']:
                        print(f"  {voice_result['voice']}: {voice_result['filename']}")
                    else:
                        print(f"  {voice_result['voice']}: ERROR - {voice_result.get('error', 'Unknown')}")
            else:
                print(f"\n✗ Failed: {result.get('error', 'Unknown error')}")
                sys.exit(1)

        finally:
            session.close()
        return

    # Handle batch modes
    if args.mode == "coverage":
        # Report on audio coverage
        print("\nAudio Coverage Report")
        print("=" * 80)
        print("This mode reports on existing audio files in the AudioQualityReview table.")
        print("Use --language to filter by language.")

        session = agent.get_session()
        try:
            from sqlalchemy import func

            # Get counts by language and voice
            if args.language:
                query = session.query(
                    AudioQualityReview.voice_name,
                    func.count(AudioQualityReview.id)
                ).filter(AudioQualityReview.language_code == args.language).group_by(
                    AudioQualityReview.voice_name
                )
                results = query.all()
                print(f"\nLanguage: {args.language}")
                for voice_name, count in results:
                    print(f"  {voice_name}: {count} audio files")
            else:
                query = session.query(
                    AudioQualityReview.language_code,
                    AudioQualityReview.voice_name,
                    func.count(AudioQualityReview.id)
                ).group_by(
                    AudioQualityReview.language_code,
                    AudioQualityReview.voice_name
                )
                results = query.all()
                current_lang = None
                for lang_code, voice_name, count in results:
                    if lang_code != current_lang:
                        print(f"\n{lang_code}:")
                        current_lang = lang_code
                    print(f"  {voice_name}: {count} audio files")
        finally:
            session.close()
        return

    elif args.mode == "check-existing":
        # List existing audio files
        print("\nExisting Audio Files")
        print("=" * 80)

        session = agent.get_session()
        try:
            query = session.query(AudioQualityReview)

            if args.language:
                query = query.filter(AudioQualityReview.language_code == args.language)

            if args.limit:
                query = query.limit(args.limit)

            audio_files = query.all()

            for audio in audio_files:
                print(f"{audio.guid} | {audio.language_code}/{audio.voice_name} | {audio.filename} | {audio.status}")

            print(f"\nTotal: {len(audio_files)} audio files")
        finally:
            session.close()
        return

    elif args.mode in ["populate-only", "regenerate"]:
        # Validate language is required
        if not args.language:
            print(f"Error: --language is required for --mode {args.mode}")
            sys.exit(1)

        # Confirm before running (unless --yes was provided)
        if not args.yes and not args.dry_run:
            # Estimate API calls
            session = agent.get_session()
            try:
                builder = LemmaQueryBuilder(session).curated_only().order_by_id()

                if args.difficulty_level is not None:
                    builder = builder.by_difficulty_level(args.difficulty_level)

                if args.limit:
                    query = builder.build().limit(args.limit)
                else:
                    query = builder.build()

                # Get all lemmas and filter by translation availability
                all_lemmas = query.all()
                lemmas_with_translation = []
                for lemma in all_lemmas:
                    if agent.get_translation_text(session, lemma, args.language):
                        lemmas_with_translation.append(lemma)

                lemma_count = len(lemmas_with_translation)
                voice_count = len(voices) if voices else 3
                estimated_calls = lemma_count * voice_count
            finally:
                session.close()

            if not confirm_operation(
                message=f"This will generate audio for {lemma_count} lemmas with {voice_count} voices each.\nTotal API calls: {estimated_calls}\nThis will use OpenAI TTS API and may incur costs.",
                estimated_calls=estimated_calls,
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                print("Aborted.")
                sys.exit(0)

        # Run batch generation
        start_time = datetime.now()
        results = agent.generate_batch(
            language_code=args.language,
            limit=args.limit,
            difficulty_level=args.difficulty_level,
            voices=voices,
        )
        duration = (datetime.now() - start_time).total_seconds()

        # Generate manifests if requested
        if args.generate_manifests:
            logger.info("Generating manifests...")
            voice_list = voices or DEFAULT_VOICES.get(args.language, [])
            for voice in voice_list:
                try:
                    manifest_path = agent.generate_manifest(args.language, voice.value)
                    logger.info(f"Generated manifest: {manifest_path}")
                except Exception as e:
                    logger.error(f"Error generating manifest for {voice.value}: {e}")

        # Print summary
        logger.info("=" * 80)
        logger.info("VIEVERSYS AGENT REPORT - Audio Generation")
        logger.info("=" * 80)
        logger.info(f"Language: {results['language_code']}")
        logger.info(f"Total lemmas: {results['total_lemmas']}")
        logger.info(f"Voices: {', '.join(results['voices'])}")
        logger.info(f"Successful: {results['success_count']}")
        logger.info(f"Errors: {results['error_count']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Output directory: {results['output_dir']}")
        logger.info("=" * 80)


if __name__ == "__main__":
    main()
