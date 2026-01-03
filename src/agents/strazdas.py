#!/usr/bin/env python3
"""
Strazdas - eSpeak-NG Audio Generation Agent

This agent generates audio files for lemmas using eSpeak-NG TTS.
Files are generated to a directory, stored with metadata in the
AudioQualityReview table with 'pending_review' status, and can later be
uploaded to S3 after review.

"Strazdas" means "thrush" in Lithuanian - a songbird known for its melodious voice.

Language documentation: https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md
"""

import argparse
import hashlib
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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
from agents.common.lemma_selection import get_lemmas_for_agent
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import DataSourceConfig, BackendType
from wordfreq.storage.models.schema import Lemma, AudioQualityReview, LemmaTranslation
from wordfreq.storage.translation_helpers import get_translation
from clients.audio import AudioFormat
from audioshoe.espeak import generate_audio, EspeakVoice, DEFAULT_ESPEAK_VOICES

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StrazdasAgent:
    """Agent for generating audio files using eSpeak-NG."""

    def __init__(
        self,
        config: DataSourceConfig,
        output_dir: str = None,
    ):
        """
        Initialize the Strazdas agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            output_dir: Output directory for generated audio (uses temp dir if None)
        """
        self.config = config
        self.debug = config.debug
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="strazdas_"))

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
        voices: List[EspeakVoice],
        create_review_record: bool = True,
        use_ipa: bool = False,
    ) -> Dict:
        """
        Generate audio files for a lemma in a specific language with multiple voices.

        Args:
            session: Database session
            lemma: Lemma to generate audio for
            language_code: Target language code
            voices: List of EspeakVoice to use
            create_review_record: Whether to create AudioQualityReview records
            use_ipa: If True and lemma has IPA, use IPA for generation

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

        # Check if we should use IPA
        ipa_text = None
        if use_ipa and hasattr(lemma, 'ipa') and lemma.ipa:
            ipa_text = lemma.ipa
            logger.info(f"Using IPA for generation: {ipa_text}")

        results = {
            "success": True,
            "lemma_guid": lemma.guid,
            "language": language_code,
            "text": text,
            "ipa_text": ipa_text,
            "voices": [],
        }

        for voice in voices:
            logger.info(f"Generating audio: {text} ({language_code}/{voice.name})")

            # Use IPA if available, otherwise use regular text
            input_text = ipa_text if ipa_text else text

            # Generate audio using eSpeak-NG
            result = generate_audio(
                text=input_text,
                voice=voice,
                ipa_input=bool(ipa_text),
            )

            if not result.success:
                logger.error(f"Failed to generate audio: {result.error}")
                results["voices"].append(
                    {
                        "voice": voice.name,
                        "success": False,
                        "error": result.error,
                    }
                )
                continue

            # Create filename and save
            safe_text = text.lower().replace(" ", "_")[:50]  # Limit length
            filename = f"{lemma.guid}_{safe_text}.mp3"

            # Create language/voice subdirectories
            # Use the voice name directly (e.g., "Ona", "Pierre")
            voice_name = voice.name
            voice_dir = self.output_dir / language_code / voice_name
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
                    session, lemma, language_code, voice_name, filename, text, md5_hash
                )

            results["voices"].append(
                {
                    "voice": voice_name,
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
        lemmas: Optional[List[Lemma]] = None,
        voices: Optional[List[EspeakVoice]] = None,
        use_ipa: bool = False,
    ) -> Dict:
        """
        Generate audio for a batch of lemmas.

        Args:
            language_code: Target language code
            lemmas: List of lemmas to process (if None, returns empty result)
            voices: Voices to use (defaults to language's default voices)
            use_ipa: If True, use IPA for generation when available

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()
        voices = voices or DEFAULT_ESPEAK_VOICES.get(language_code, [])

        try:
            # If no lemmas provided, return empty result
            if not lemmas:
                return {
                    "language_code": language_code,
                    "total_lemmas": 0,
                    "voices": [v.name for v in voices],
                    "output_dir": str(self.output_dir),
                    "lemmas": [],
                    "success_count": 0,
                    "error_count": 0,
                }

            # Filter to only lemmas that have translations in the target language
            lemmas_with_translation = []
            for lemma in lemmas:
                if self.get_translation_text(session, lemma, language_code):
                    lemmas_with_translation.append(lemma)

            lemmas = lemmas_with_translation

            logger.info(f"Generating audio for {len(lemmas)} lemmas in {language_code}")

            results = {
                "language_code": language_code,
                "total_lemmas": len(lemmas),
                "voices": [v.name for v in voices],
                "output_dir": str(self.output_dir),
                "lemmas": [],
                "success_count": 0,
                "error_count": 0,
            }

            for i, lemma in enumerate(lemmas, 1):
                logger.info(f"[{i}/{len(lemmas)}] Processing {lemma.guid}")

                result = self.generate_audio_for_lemma(
                    session, lemma, language_code, voices, create_review_record=True, use_ipa=use_ipa
                )

                results["lemmas"].append(result)
                if result["success"]:
                    results["success_count"] += 1
                else:
                    results["error_count"] += 1

            return results

        finally:
            session.close()


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Strazdas - eSpeak-NG Audio Generation Agent")

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

    # Strazdas-specific arguments
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
        help="Voice names to use (e.g., Ona Jonas Ruta for Lithuanian). Use --list-voices to see available voices.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available voices for each language and exit",
    )
    parser.add_argument(
        "--use-ipa",
        action="store_true",
        help="Use IPA phonetic notation for generation when available",
    )

    return parser


def main():
    """Main entry point for the strazdas agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Handle --list-voices
    if args.list_voices:
        print("\nAvailable eSpeak-NG Voices by Language:")
        print("=" * 60)
        for lang_code in ["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi"]:
            voices = EspeakVoice.get_voices_for_language(lang_code)
            print(f"\n{lang_code.upper()}:")
            for voice in voices:
                gender_str = "Female" if voice.gender == "f" else "Male"
                print(f"  {voice.name:12} - {gender_str:6} (variant {voice.variant})")
        print("\n" + "=" * 60)
        sys.exit(0)

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Validate mode-specific requirements
    if args.mode in ["populate-only", "regenerate"] and not args.language:
        print(f"Error: --language is required for --mode {args.mode}")
        sys.exit(1)

    # Create agent with config
    agent = StrazdasAgent(
        config=config,
        output_dir=args.output_dir,
    )

    # Convert voice names to EspeakVoice enums
    voices = None
    if args.voices:
        try:
            voices = [EspeakVoice[v.upper()] for v in args.voices]
        except KeyError as e:
            print(f"Error: Unknown voice name: {e}")
            print(f"Use --list-voices to see available voices")
            sys.exit(1)

    # Get lemmas to process (either single lemma from --guid or batch)
    # Only needed for modes that process lemmas (not coverage or check-existing)
    lemmas = None
    if args.mode in ["populate-only", "regenerate"] or args.guid:
        # Require language for lemma processing
        if not args.language:
            print("Error: --language is required for lemma processing")
            sys.exit(1)

        session = agent.get_session()
        try:
            lemmas = get_lemmas_for_agent(session, args)
        finally:
            session.close()

        # Show what we're processing
        if len(lemmas) == 1:
            lemma = lemmas[0]
            print(f"\nProcessing audio for: {lemma.lemma_text} (GUID: {lemma.guid})")
            print(f"POS: {lemma.pos_type}")

            # Check if translation exists
            session = agent.get_session()
            try:
                translation = agent.get_translation_text(session, lemma, args.language)
            finally:
                session.close()

            if not translation:
                print(f"Error: No {args.language} translation found for this lemma")
                sys.exit(1)

            print(f"Translation ({args.language}): {translation}")

            # Use default voices if not specified
            voice_list = voices or DEFAULT_ESPEAK_VOICES.get(args.language, [])
            print(f"\nGenerating audio with voices: {', '.join(v.name for v in voice_list)}")

            # Generate audio for the single lemma
            session = agent.get_session()
            try:
                result = agent.generate_audio_for_lemma(
                    session, lemma, args.language, voice_list, create_review_record=True, use_ipa=args.use_ipa
                )
            finally:
                session.close()

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
            return
        elif len(lemmas) == 0:
            print("\nNo lemmas found to process")
            sys.exit(1)

    # Handle batch modes
    if args.mode == "coverage":
        # Report on audio coverage
        print("\nAudio Coverage Report (eSpeak-NG)")
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
        print("\nExisting Audio Files (eSpeak-NG)")
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
            # Count lemmas with translations
            session = agent.get_session()
            try:
                lemmas_with_translation = []
                for lemma in lemmas:
                    if agent.get_translation_text(session, lemma, args.language):
                        lemmas_with_translation.append(lemma)
                lemma_count = len(lemmas_with_translation)
            finally:
                session.close()

            voice_list = voices or DEFAULT_ESPEAK_VOICES.get(args.language, [])
            voice_count = len(voice_list)
            estimated_files = lemma_count * voice_count

            voices_str = ', '.join(v.name for v in voices) if voices else ', '.join(v.name for v in voice_list)
            if not confirm_operation(
                message=f"This will generate audio for {lemma_count} lemmas with {voice_count} voices each.\nTotal files: {estimated_files}\nVoices: {voices_str}\nThis will use eSpeak-NG TTS (free, local generation).",
                estimated_calls=None,  # No API calls, local generation
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                print("Aborted.")
                sys.exit(0)

        # Run batch generation
        start_time = datetime.now()
        results = agent.generate_batch(
            language_code=args.language,
            lemmas=lemmas,
            voices=voices,
            use_ipa=args.use_ipa,
        )
        duration = (datetime.now() - start_time).total_seconds()

        # Print summary
        logger.info("=" * 80)
        logger.info("STRAZDAS AGENT REPORT - eSpeak-NG Audio Generation")
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
