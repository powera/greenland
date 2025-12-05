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
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, AudioQualityReview, LemmaTranslation
from clients.audio import AudioFormat
from audioshoe.espeak import generate_audio, EspeakVoice, DEFAULT_ESPEAK_VOICES

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Language column mapping for direct translation columns
LANGUAGE_COLUMN_MAP = {
    "zh": "chinese_translation",
    "ko": "korean_translation",
    "fr": "french_translation",
    "sw": "swahili_translation",
    "lt": "lithuanian_translation",
    "vi": "vietnamese_translation",
}


class StrazdasAgent:
    """Agent for generating audio files using eSpeak-NG."""

    def __init__(
        self,
        db_path: str = None,
        output_dir: str = None,
        debug: bool = False,
    ):
        """
        Initialize the Strazdas agent.

        Args:
            db_path: Database path (uses default if None)
            output_dir: Output directory for generated audio (uses temp dir if None)
            debug: Enable debug logging
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="strazdas_"))
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {self.output_dir}")

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

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
        # Check if this is a column-based translation
        if language_code in LANGUAGE_COLUMN_MAP:
            column_name = LANGUAGE_COLUMN_MAP[language_code]
            return getattr(lemma, column_name, None)

        # Otherwise, check table-based translations (es, de, pt)
        translation = (
            session.query(LemmaTranslation)
            .filter_by(lemma_id=lemma.id, language_code=language_code)
            .first()
        )
        return translation.translation if translation else None

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
        limit: Optional[int] = None,
        difficulty_level: Optional[int] = None,
        voices: Optional[List[EspeakVoice]] = None,
        use_ipa: bool = False,
    ) -> Dict:
        """
        Generate audio for a batch of lemmas.

        Args:
            language_code: Target language code
            limit: Maximum number of lemmas to process
            difficulty_level: Filter by difficulty level
            voices: Voices to use (defaults to language's default voices)
            use_ipa: If True, use IPA for generation when available

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()
        voices = voices or DEFAULT_ESPEAK_VOICES.get(language_code, [])

        try:
            # Build query
            query = session.query(Lemma).filter(Lemma.guid.isnot(None))

            # Filter by difficulty level if specified
            if difficulty_level is not None:
                query = query.filter(Lemma.difficulty_level == difficulty_level)

            # Filter lemmas that have translation in target language
            if language_code in LANGUAGE_COLUMN_MAP:
                column_name = LANGUAGE_COLUMN_MAP[language_code]
                query = query.filter(getattr(Lemma, column_name).isnot(None))
            else:
                # For table-based translations
                query = query.join(LemmaTranslation).filter(
                    LemmaTranslation.language_code == language_code
                )

            # Apply limit
            if limit:
                query = query.limit(limit)

            lemmas = query.all()
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
    parser.add_argument("--db-path", help="Database path (uses default if not specified)")
    parser.add_argument("--output-dir", help="Output directory for generated audio")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--language",
        required=True,
        choices=["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi"],
        help="Target language code",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of lemmas to process")
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
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt before generating audio",
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

    # Convert voice names to EspeakVoice enums
    voices = None
    if args.voices:
        try:
            voices = [EspeakVoice[v.upper()] for v in args.voices]
        except KeyError as e:
            print(f"Error: Unknown voice name: {e}")
            print(f"Use --list-voices to see available voices for {args.language}")
            sys.exit(1)

    # Confirm before running (unless --yes was provided)
    if not args.yes:
        # Estimate number of files
        agent_temp = StrazdasAgent(db_path=args.db_path, debug=args.debug)
        session = agent_temp.get_session()
        try:
            query = session.query(Lemma).filter(Lemma.guid.isnot(None))

            if args.difficulty_level is not None:
                query = query.filter(Lemma.difficulty_level == args.difficulty_level)

            if args.language in LANGUAGE_COLUMN_MAP:
                column_name = LANGUAGE_COLUMN_MAP[args.language]
                query = query.filter(getattr(Lemma, column_name).isnot(None))

            if args.limit:
                query = query.limit(args.limit)

            lemma_count = query.count()
            voice_list = voices or DEFAULT_ESPEAK_VOICES.get(args.language, [])
            voice_count = len(voice_list)
            estimated_files = lemma_count * voice_count
        finally:
            session.close()

        print(f"\nThis will generate audio for {lemma_count} lemmas with {voice_count} voices each.")
        print(f"Total files: {estimated_files}")
        if voices:
            print(f"Voices: {', '.join(v.name for v in voices)}")
        print(f"This will use eSpeak-NG TTS (free, local generation).")
        response = input("Do you want to proceed? [y/N]: ").strip().lower()

        if response not in ["y", "yes"]:
            print("Aborted.")
            sys.exit(0)

        print()  # Extra newline for readability

    # Create agent and run generation
    agent = StrazdasAgent(
        db_path=args.db_path,
        output_dir=args.output_dir,
        debug=args.debug,
    )

    start_time = datetime.now()
    results = agent.generate_batch(
        language_code=args.language,
        limit=args.limit,
        difficulty_level=args.difficulty_level,
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
