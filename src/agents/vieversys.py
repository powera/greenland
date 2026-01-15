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
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_llm_args,
    add_processing_args,
    confirm_operation,
    get_data_source_config,
)
from agents.common.lemma_selection import (
    LemmaQueryBuilder,
    apply_limit_and_sample_rate,
    get_lemmas_for_agent,
)
from clients.audio import AudioFormat, Voice, generate_audio
from clients.audio.manifest import generate_manifest
from clients.audio.s3_uploader import S3AudioUploader
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import (
    AudioQualityReview,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.storage.translation_helpers import get_translation

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
        upload_s3: bool = False,
    ):
        """
        Initialize the Vieversys agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            output_dir: Output directory for generated audio (uses temp dir if None)
            upload_s3: Whether to upload generated audio to S3 staging
        """
        self.config = config
        self.debug = config.debug
        self.upload_s3 = upload_s3
        self.output_dir = (
            Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="vieversys_"))
        )

        if self.debug:
            logger.setLevel(logging.DEBUG)

        # Initialize S3 uploader if needed
        self.s3_uploader = None
        if self.upload_s3:
            try:
                self.s3_uploader = S3AudioUploader()
                logger.info("S3 uploader initialized")
            except Exception as e:
                logger.error(f"Failed to initialize S3 uploader: {e}")
                logger.warning("S3 upload will be disabled")
                self.upload_s3 = False

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

            # Upload to S3 staging if enabled
            s3_staging_url = None
            s3_staging_manifest_url = None
            if self.upload_s3 and self.s3_uploader:
                # Generate manifest
                manifest_data = generate_manifest(
                    audio_file_path=file_path,
                    agent="vieversys",
                    voice_name=voice.value,
                    language_code=language_code,
                    expected_text=text,
                    guid=lemma.guid,
                    sentence_id=None,
                    grammatical_form=None,
                    generation_params={
                        "model": result.model,
                    },
                )

                # Upload to staging
                success, audio_url, manifest_url, _ = self.s3_uploader.upload_to_staging(
                    audio_path=file_path,
                    manifest_data=manifest_data,
                    agent="vieversys",
                    check_existing=True,
                )

                if success:
                    s3_staging_url = audio_url
                    s3_staging_manifest_url = manifest_url
                    logger.info(f"Uploaded to S3 staging: {audio_url}")
                else:
                    logger.error(f"Failed to upload to S3 staging: {file_path}")

            # Create review record if requested
            if create_review_record:
                self._create_review_record(
                    session,
                    lemma,
                    language_code,
                    voice.value,
                    filename,
                    text,
                    md5_hash,
                    s3_staging_url=s3_staging_url,
                    s3_staging_manifest_url=s3_staging_manifest_url,
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
        s3_staging_url: Optional[str] = None,
        s3_staging_manifest_url: Optional[str] = None,
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
            existing.s3_staging_url = s3_staging_url
            existing.s3_staging_manifest_url = s3_staging_manifest_url
            existing.staging_agent = "vieversys" if s3_staging_url else None
            existing.s3_prod_url = None  # Clear prod URL when regenerating
            existing.accepted_at = None
            existing.accepted_by = None
            logger.debug(f"Updated existing review record for {lemma.guid}")
        else:
            # Create new record
            review = AudioQualityReview(
                guid=lemma.guid,
                sentence_id=None,  # This is lemma audio, not sentence audio
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=None,  # Base form (not generating derivative forms)
                filename=filename,
                expected_text=text,
                manifest_md5=md5_hash,
                s3_staging_url=s3_staging_url,
                s3_staging_manifest_url=s3_staging_manifest_url,
                s3_prod_url=None,
                staging_agent="vieversys" if s3_staging_url else None,
                lemma_id=lemma.id,
                status="pending_review",
            )
            session.add(review)
            logger.debug(f"Created review record for {lemma.guid}")

        session.commit()

    def generate_audio_for_sentence(
        self,
        session,
        sentence: Sentence,
        sentence_translation: SentenceTranslation,
        voices: List[Voice],
        create_review_record: bool = True,
    ) -> Dict:
        """
        Generate audio files for a sentence in a specific language with multiple voices.

        Args:
            session: Database session
            sentence: Sentence to generate audio for
            sentence_translation: SentenceTranslation with the text to speak
            voices: List of voices to use
            create_review_record: Whether to create AudioQualityReview records

        Returns:
            Dict with generation results
        """
        text = sentence_translation.translation_text
        language_code = sentence_translation.language_code

        results = {
            "success": True,
            "sentence_id": sentence.id,
            "language": language_code,
            "text": text,
            "voices": [],
        }

        for voice in voices:
            logger.info(f"Generating audio: {text} ({language_code}/{voice.value})")

            # Generate audio (with is_sentence=True for natural sentence pacing)
            result = generate_audio(
                text=text, voice=voice, language_code=language_code, is_sentence=True
            )

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
            filename = f"sent_{sentence.id}_{safe_text}.mp3"

            # Create language/voice subdirectories
            voice_dir = self.output_dir / language_code / voice.value
            voice_dir.mkdir(parents=True, exist_ok=True)

            file_path = voice_dir / filename

            # Write audio data
            file_path.write_bytes(result.audio_data)

            # Calculate MD5
            md5_hash = hashlib.md5(result.audio_data).hexdigest()

            logger.info(f"Saved audio: {file_path} (MD5: {md5_hash})")

            # Upload to S3 staging if enabled
            s3_staging_url = None
            s3_staging_manifest_url = None
            if self.upload_s3 and self.s3_uploader:
                # Generate manifest
                manifest_data = generate_manifest(
                    audio_file_path=file_path,
                    agent="vieversys",
                    voice_name=voice.value,
                    language_code=language_code,
                    expected_text=text,
                    guid=None,  # Sentences don't have GUIDs
                    sentence_id=sentence.id,
                    grammatical_form=None,
                    generation_params={
                        "model": result.model,
                    },
                )

                # Upload to staging
                success, audio_url, manifest_url, _ = self.s3_uploader.upload_to_staging(
                    audio_path=file_path,
                    manifest_data=manifest_data,
                    agent="vieversys",
                    check_existing=True,
                )

                if success:
                    s3_staging_url = audio_url
                    s3_staging_manifest_url = manifest_url
                    logger.info(f"Uploaded to S3 staging: {audio_url}")
                else:
                    logger.error(f"Failed to upload to S3 staging: {file_path}")

            # Create review record if requested
            if create_review_record:
                self._create_sentence_review_record(
                    session,
                    sentence,
                    language_code,
                    voice.value,
                    filename,
                    text,
                    md5_hash,
                    s3_staging_url=s3_staging_url,
                    s3_staging_manifest_url=s3_staging_manifest_url,
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

    def _create_sentence_review_record(
        self,
        session,
        sentence: Sentence,
        language_code: str,
        voice_name: str,
        filename: str,
        text: str,
        md5_hash: str,
        s3_staging_url: Optional[str] = None,
        s3_staging_manifest_url: Optional[str] = None,
    ):
        """Create AudioQualityReview record for generated sentence audio."""
        # Check if record already exists
        existing = (
            session.query(AudioQualityReview)
            .filter_by(
                sentence_id=sentence.id,
                language_code=language_code,
                voice_name=voice_name,
            )
            .first()
        )

        if existing:
            # Update existing record
            existing.filename = filename
            existing.expected_text = text
            existing.manifest_md5 = md5_hash
            existing.status = "pending_review"
            existing.s3_staging_url = s3_staging_url
            existing.s3_staging_manifest_url = s3_staging_manifest_url
            existing.staging_agent = "vieversys" if s3_staging_url else None
            existing.s3_prod_url = None  # Clear prod URL when regenerating
            existing.accepted_at = None
            existing.accepted_by = None
            logger.debug(f"Updated existing review record for sentence {sentence.id}")
        else:
            # Create new record
            review = AudioQualityReview(
                guid=f"S_{sentence.id:05d}",  # Synthetic GUID for sentences
                sentence_id=sentence.id,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=None,
                filename=filename,
                expected_text=text,
                manifest_md5=md5_hash,
                s3_staging_url=s3_staging_url,
                s3_staging_manifest_url=s3_staging_manifest_url,
                s3_prod_url=None,
                staging_agent="vieversys" if s3_staging_url else None,
                lemma_id=None,
                status="pending_review",
            )
            session.add(review)
            logger.debug(f"Created review record for sentence {sentence.id}")

        session.commit()

    def generate_batch(
        self,
        language_code: str,
        lemmas: Optional[List[Lemma]] = None,
        voices: Optional[List[Voice]] = None,
    ) -> Dict:
        """
        Generate audio for a batch of lemmas.

        Args:
            language_code: Target language code
            lemmas: List of lemmas to process (if None, returns empty result)
            voices: Voices to use (defaults to language's default voices)

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()
        voices = voices or DEFAULT_VOICES.get(language_code, [Voice.ASH, Voice.ALLOY, Voice.NOVA])

        try:
            # If no lemmas provided, return empty result
            if not lemmas:
                return {
                    "language_code": language_code,
                    "total_lemmas": 0,
                    "voices": [v.value for v in voices],
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

    def generate_sentences_batch(
        self,
        language_code: str,
        guid: Optional[str] = None,
        limit: int = 10,
        voices: Optional[List[Voice]] = None,
    ) -> Dict:
        """
        Generate audio for sentences.

        Args:
            language_code: Target language code
            guid: Optional GUID to filter sentences by (sentences that use this lemma)
            limit: Maximum number of sentences to process per language (default: 10)
            voices: Voices to use (defaults to language's default voices)

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()
        voices = voices or DEFAULT_VOICES.get(language_code, [Voice.ASH, Voice.ALLOY, Voice.NOVA])

        try:
            # Build query for sentences
            query = (
                session.query(Sentence, SentenceTranslation)
                .join(SentenceTranslation, Sentence.id == SentenceTranslation.sentence_id)
                .filter(
                    SentenceTranslation.language_code == language_code,
                    Sentence.rejected == False,  # noqa: E712
                )
            )

            # Filter by GUID if specified (sentences that use this lemma)
            if guid:
                # Use a subquery to find distinct sentence IDs that contain this lemma
                # This prevents duplicates when a sentence uses the same lemma multiple times
                sentence_ids_subquery = (
                    session.query(SentenceWord.sentence_id)
                    .join(Lemma, SentenceWord.lemma_id == Lemma.id)
                    .filter(Lemma.guid == guid)
                    .distinct()
                    .subquery()
                )
                query = query.filter(Sentence.id.in_(sentence_ids_subquery))

            # Order by sentence ID and limit
            query = query.order_by(Sentence.id).limit(limit)

            sentence_pairs = query.all()

            if not sentence_pairs:
                return {
                    "language_code": language_code,
                    "guid": guid,
                    "total_sentences": 0,
                    "voices": [v.value for v in voices],
                    "output_dir": str(self.output_dir),
                    "sentences": [],
                    "success_count": 0,
                    "error_count": 0,
                }

            logger.info(f"Generating audio for {len(sentence_pairs)} sentences in {language_code}")

            results = {
                "language_code": language_code,
                "guid": guid,
                "total_sentences": len(sentence_pairs),
                "voices": [v.value for v in voices],
                "output_dir": str(self.output_dir),
                "sentences": [],
                "success_count": 0,
                "error_count": 0,
            }

            for i, (sentence, translation) in enumerate(sentence_pairs, 1):
                logger.info(f"[{i}/{len(sentence_pairs)}] Processing sentence {sentence.id}")

                result = self.generate_audio_for_sentence(
                    session, sentence, translation, voices, create_review_record=True
                )

                results["sentences"].append(result)
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
    parser.add_argument("--difficulty-level", type=int, help="Filter by difficulty level (1-20)")
    parser.add_argument(
        "--voices",
        nargs="+",
        choices=[
            "ash",
            "alloy",
            "nova",
            "ballad",
            "coral",
            "echo",
            "fable",
            "onyx",
            "sage",
            "shimmer",
        ],
        help="Voices to use (defaults to ash, alloy, nova)",
    )
    parser.add_argument(
        "--generate-manifests",
        action="store_true",
        help="[DEPRECATED] Generate audio_manifest.json files after generation",
    )
    parser.add_argument(
        "--upload-s3",
        action="store_true",
        help="Upload generated audio and manifests to S3 staging bucket",
    )
    parser.add_argument(
        "--generate-sentences",
        action="store_true",
        help="Generate audio for sentences (instead of lemmas)",
    )
    parser.add_argument(
        "--sentence-limit",
        type=int,
        default=10,
        help="Maximum number of sentences to process per language (default: 10)",
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
        upload_s3=args.upload_s3,
    )

    # Convert voice names to Voice enums
    voices = None
    if args.voices:
        voices = [Voice(v) for v in args.voices]

    # Get lemmas to process (either single lemma from --guid or batch)
    # Only needed for modes that process lemmas (not coverage or check-existing)
    lemmas = None
    if args.mode in ["populate-only", "regenerate"]:
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
        elif len(lemmas) == 0:
            print("\nNo lemmas found to process")
            sys.exit(1)
        else:
            print(f"\nProcessing audio for {len(lemmas)} lemmas")

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
                query = (
                    session.query(AudioQualityReview.voice_name, func.count(AudioQualityReview.id))
                    .filter(AudioQualityReview.language_code == args.language)
                    .group_by(AudioQualityReview.voice_name)
                )
                results = query.all()
                print(f"\nLanguage: {args.language}")
                for voice_name, count in results:
                    print(f"  {voice_name}: {count} audio files")
            else:
                query = session.query(
                    AudioQualityReview.language_code,
                    AudioQualityReview.voice_name,
                    func.count(AudioQualityReview.id),
                ).group_by(AudioQualityReview.language_code, AudioQualityReview.voice_name)
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
                print(
                    f"{audio.guid} | {audio.language_code}/{audio.voice_name} | {audio.filename} | {audio.status}"
                )

            print(f"\nTotal: {len(audio_files)} audio files")
        finally:
            session.close()
        return

    elif args.mode in ["populate-only", "regenerate"]:
        # Validate language is required
        if not args.language:
            print(f"Error: --language is required for --mode {args.mode}")
            sys.exit(1)

        # Check if we're generating sentences or lemmas
        if args.generate_sentences:
            # Generate audio for sentences
            voice_count = len(voices) if voices else 3
            estimated_calls = args.sentence_limit * voice_count

            # Confirm before running (unless --yes was provided)
            if not args.yes and not args.dry_run:
                guid_msg = f" for lemma {args.guid}" if args.guid else ""
                if not confirm_operation(
                    message=f"This will generate audio for up to {args.sentence_limit} sentences{guid_msg} with {voice_count} voices each.\nTotal API calls: ~{estimated_calls}\nThis will use OpenAI TTS API and may incur costs.",
                    estimated_calls=estimated_calls,
                    skip_confirmation=args.yes,
                    dry_run=args.dry_run,
                ):
                    print("Aborted.")
                    sys.exit(0)

            # Run sentence batch generation
            start_time = datetime.now()
            results = agent.generate_sentences_batch(
                language_code=args.language,
                guid=args.guid,
                limit=args.sentence_limit,
                voices=voices,
            )
            duration = (datetime.now() - start_time).total_seconds()

            # Print summary
            logger.info("=" * 80)
            logger.info("VIEVERSYS AGENT REPORT - Sentence Audio Generation")
            logger.info("=" * 80)
            logger.info(f"Language: {results['language_code']}")
            if results.get("guid"):
                logger.info(f"GUID: {results['guid']}")
            logger.info(f"Total sentences: {results['total_sentences']}")
            logger.info(f"Voices: {', '.join(results['voices'])}")
            logger.info(f"Successful: {results['success_count']}")
            logger.info(f"Errors: {results['error_count']}")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info(f"Output directory: {results['output_dir']}")
            logger.info("=" * 80)
            return

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

            voice_count = len(voices) if voices else 3
            estimated_calls = lemma_count * voice_count

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
            lemmas=lemmas,
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
