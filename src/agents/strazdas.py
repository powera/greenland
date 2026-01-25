#!/usr/bin/env python3
"""
Strazdas - Local Audio Generation Agent

This agent generates audio files for lemmas using local TTS engines.
Files are generated to a directory, stored with metadata in the
AudioQualityReview table with 'pending_review' status, and can later be
uploaded to S3 after review.

"Strazdas" means "thrush" in Lithuanian - a songbird known for its melodious voice.

Supported TTS backends:
- espeak: eSpeak-NG with MBROLA voices (fast, lightweight, all languages)
- qwen: Qwen3-TTS neural TTS (high quality, CJK + FIGS + PT)
- piper: Piper neural TTS (good quality, select languages)

Each backend has different voice options and language support.
Use --list-voices to see available voices for each backend.

Backend documentation:
- eSpeak-NG: https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md
- Qwen3-TTS: https://github.com/QwenLM/Qwen3-TTS
- Piper: https://github.com/rhasspy/piper
"""

import argparse
import hashlib
import logging
import sys
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

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
from agents.common.lemma_selection import get_lemmas_for_agent
from audioshoe.espeak import DEFAULT_ESPEAK_VOICES, EspeakVoice
from audioshoe.espeak import generate_audio as espeak_generate_audio
from audioshoe.qwen import DEFAULT_QWEN_VOICES, QwenVoice
from audioshoe.qwen import generate_audio as qwen_generate_audio
from clients.audio import AudioFormat
from clients.audio.manifest import generate_manifest
from clients.audio.s3_uploader import S3AudioUploader
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import AudioQualityReview, Lemma, LemmaTranslation
from wordfreq.storage.translation_helpers import get_translation

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TtsBackend(Enum):
    """Available TTS backends for audio generation."""

    ESPEAK = "espeak"  # eSpeak-NG with MBROLA voices
    QWEN = "qwen"  # Qwen3-TTS neural TTS
    # PIPER = "piper"  # Piper neural TTS (future)

    @classmethod
    def from_string(cls, value: str) -> "TtsBackend":
        """Convert string to TtsBackend enum."""
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Unknown TTS backend: {value}. Available: {[b.value for b in cls]}")


# Type alias for voice types
VoiceType = Union[EspeakVoice, QwenVoice]

# Backend-specific language support
BACKEND_LANGUAGES = {
    TtsBackend.ESPEAK: ["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi"],
    TtsBackend.QWEN: ["zh", "ja", "ko", "fr", "it", "de", "es", "pt"],
}

# Backend-specific default voices
BACKEND_DEFAULT_VOICES: Dict[TtsBackend, Dict[str, List[VoiceType]]] = {
    TtsBackend.ESPEAK: DEFAULT_ESPEAK_VOICES,  # type: ignore[dict-item]
    TtsBackend.QWEN: DEFAULT_QWEN_VOICES,  # type: ignore[dict-item]
}


class StrazdasAgent:
    """Agent for generating audio files using local TTS engines."""

    def __init__(
        self,
        config: DataSourceConfig,
        output_dir: Optional[str] = None,
        upload_s3: bool = False,
        tts_backend: TtsBackend = TtsBackend.ESPEAK,
    ) -> None:
        """
        Initialize the Strazdas agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            output_dir: Output directory for generated audio (uses temp dir if None)
            upload_s3: Whether to upload generated audio to S3 staging
            tts_backend: TTS backend to use (espeak, qwen)
        """
        self.config = config
        self.debug = config.debug
        self.upload_s3 = upload_s3
        self.tts_backend = tts_backend
        self.output_dir = (
            Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="strazdas_"))
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

    def get_session(self) -> Session:
        """Get database session using backend abstraction."""
        return create_backend_session(self.config)

    def get_translation_text(
        self, session: Session, lemma: Lemma, language_code: str
    ) -> Optional[str]:
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
        session: Session,
        lemma: Lemma,
        language_code: str,
        voices: List[VoiceType],
        create_review_record: bool = True,
        use_ipa: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate audio files for a lemma in a specific language with multiple voices.

        Args:
            session: Database session
            lemma: Lemma to generate audio for
            language_code: Target language code
            voices: List of voice objects (EspeakVoice or QwenVoice)
            create_review_record: Whether to create AudioQualityReview records
            use_ipa: If True and lemma has IPA, use IPA for generation (eSpeak only)

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

        # Check if we should use IPA (only supported for eSpeak)
        ipa_text = None
        if use_ipa and self.tts_backend == TtsBackend.ESPEAK:
            if hasattr(lemma, "ipa") and lemma.ipa:
                ipa_text = lemma.ipa
                logger.info(f"Using IPA for generation: {ipa_text}")

        results = {
            "success": True,
            "lemma_guid": lemma.guid,
            "language": language_code,
            "text": text,
            "ipa_text": ipa_text,
            "backend": self.tts_backend.value,
            "voices": [],
        }

        for voice in voices:
            logger.info(
                f"Generating audio: {text} ({language_code}/{voice.name}) "
                f"[{self.tts_backend.value}]"
            )

            # Use IPA if available (eSpeak only), otherwise use regular text
            input_text = ipa_text if ipa_text else text

            # Generate audio using the configured backend
            result = self._generate_audio_with_backend(voice, input_text, ipa_text)

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
            # Use the voice ui_name for unique identification (e.g., "qwen-zh-f1")
            voice_name = voice.ui_name if hasattr(voice, "ui_name") else voice.name
            voice_dir = self.output_dir / language_code / voice_name
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
                # Generate manifest with backend-specific params
                generation_params = self._get_generation_params(voice, ipa_text)

                manifest_data = generate_manifest(
                    audio_file_path=file_path,
                    agent="strazdas",
                    voice_name=voice_name,
                    language_code=language_code,
                    expected_text=text,
                    guid=lemma.guid,
                    sentence_id=None,
                    grammatical_form=None,
                    generation_params=generation_params,
                )

                # Upload to staging
                success, audio_url, manifest_url, _ = self.s3_uploader.upload_to_staging(
                    audio_path=file_path,
                    manifest_data=manifest_data,
                    agent="strazdas",
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
                    voice_name,
                    filename,
                    text,
                    md5_hash,
                    s3_staging_url=s3_staging_url,
                    s3_staging_manifest_url=s3_staging_manifest_url,
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

    def _generate_audio_with_backend(
        self,
        voice: VoiceType,
        text: str,
        ipa_text: Optional[str],
    ) -> Any:
        """
        Generate audio using the configured TTS backend.

        Args:
            voice: Voice object (EspeakVoice or QwenVoice)
            text: Text to synthesize
            ipa_text: IPA text (eSpeak only)

        Returns:
            AudioGenerationResult from the backend
        """
        if self.tts_backend == TtsBackend.ESPEAK:
            return espeak_generate_audio(
                text=text,
                voice=voice,  # type: ignore[arg-type]
                ipa_input=bool(ipa_text),
            )
        elif self.tts_backend == TtsBackend.QWEN:
            return qwen_generate_audio(
                text=text,
                voice=voice,  # type: ignore[arg-type]
            )
        else:
            raise ValueError(f"Unsupported TTS backend: {self.tts_backend}")

    def _get_generation_params(
        self,
        voice: VoiceType,
        ipa_text: Optional[str],
    ) -> Dict[str, Any]:
        """
        Get generation parameters for manifest based on backend.

        Args:
            voice: Voice object
            ipa_text: IPA text (if used)

        Returns:
            Dict of generation parameters
        """
        if self.tts_backend == TtsBackend.ESPEAK:
            return {
                "backend": "espeak",
                "voice": voice.espeak_identifier if hasattr(voice, "espeak_identifier") else voice.name,  # type: ignore[union-attr]
                "ipa_input": bool(ipa_text),
            }
        elif self.tts_backend == TtsBackend.QWEN:
            return {
                "backend": "qwen",
                "voice": voice.ui_name if hasattr(voice, "ui_name") else voice.name,
                "model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            }
        else:
            return {"backend": self.tts_backend.value, "voice": voice.name}

    def _create_review_record(
        self,
        session: Session,
        lemma: Lemma,
        language_code: str,
        voice_name: str,
        filename: str,
        text: str,
        md5_hash: str,
        s3_staging_url: Optional[str] = None,
        s3_staging_manifest_url: Optional[str] = None,
    ) -> None:
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
            existing.staging_agent = "strazdas" if s3_staging_url else None
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
                staging_agent="strazdas" if s3_staging_url else None,
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
        voices: Optional[List[VoiceType]] = None,
        use_ipa: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate audio for a batch of lemmas.

        Args:
            language_code: Target language code
            lemmas: List of lemmas to process (if None, returns empty result)
            voices: Voices to use (defaults to backend's default voices for language)
            use_ipa: If True, use IPA for generation when available (eSpeak only)

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()

        # Get default voices for the configured backend
        if voices is None:
            backend_voices = BACKEND_DEFAULT_VOICES.get(self.tts_backend, {})
            voices = backend_voices.get(language_code, [])

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

            results: Dict[str, Any] = {
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
                    session,
                    lemma,
                    language_code,
                    voices,
                    create_review_record=True,
                    use_ipa=use_ipa,
                )

                results["lemmas"].append(result)
                if result["success"]:
                    results["success_count"] += 1
                else:
                    results["error_count"] += 1

            return results

        finally:
            session.close()


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Strazdas - Local Audio Generation Agent")

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

    # TTS backend selection
    parser.add_argument(
        "--tts-backend",
        choices=["espeak", "qwen"],
        default="espeak",
        help="TTS backend to use: espeak (fast, all languages), qwen (neural, CJK+FIGS+PT). Default: espeak",
    )

    # Strazdas-specific arguments
    parser.add_argument("--output-dir", help="Output directory for generated audio")
    parser.add_argument(
        "--language",
        choices=["lt", "zh", "ja", "ko", "fr", "it", "de", "es", "pt", "sw", "vi"],
        help="Target language code (required for populate-only and regenerate modes)",
    )
    parser.add_argument("--difficulty-level", type=int, help="Filter by difficulty level (1-20)")
    parser.add_argument(
        "--voices",
        nargs="+",
        help="Voice names to use. Use --list-voices to see available voices for each backend.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available voices for each TTS backend and exit",
    )
    parser.add_argument(
        "--use-ipa",
        action="store_true",
        help="Use IPA phonetic notation for generation when available (eSpeak only)",
    )
    parser.add_argument(
        "--upload-s3",
        action="store_true",
        help="Upload generated audio and manifests to S3 staging bucket",
    )

    return parser


def main() -> None:
    """Main entry point for the strazdas agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Handle --list-voices
    if args.list_voices:
        print("\n" + "=" * 70)
        print("AVAILABLE TTS VOICES BY BACKEND")
        print("=" * 70)

        # eSpeak voices
        print("\n[ESPEAK] eSpeak-NG with MBROLA voices")
        print("-" * 70)
        print("Languages: lt, zh, ko, fr, de, es, pt, sw, vi")
        print("Usage: --tts-backend espeak --voices ONA JONAS")
        for lang_code in ["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi"]:
            espeak_voices = EspeakVoice.get_voices_for_language(lang_code)
            if espeak_voices:
                print(f"\n  {lang_code.upper()}:")
                for ev in espeak_voices:
                    gender_str = "F" if ev.gender == "f" else "M"
                    print(f"    {ev.name:12} ({gender_str}, variant {ev.variant})")

        # Qwen voices
        print("\n" + "-" * 70)
        print("[QWEN] Qwen3-TTS Neural TTS (high quality)")
        print("-" * 70)
        print("Languages: zh, ja, ko, fr, it, de, es, pt")
        print("Usage: --tts-backend qwen --voices QWEN_ZH_F1 QWEN_ZH_M2")
        print("Voice types: f1=soprano, f2=alto, m1=tenor, m2=bass")
        for lang_code in ["zh", "ja", "ko", "fr", "it", "de", "es", "pt"]:
            qwen_voices = QwenVoice.get_voices_for_language(lang_code)
            if qwen_voices:
                print(f"\n  {lang_code.upper()}:")
                for qv in qwen_voices:
                    gender_str = "F" if qv.gender == "f" else "M"
                    print(f"    {qv.name:16} ({gender_str}, {qv.pitch_type})")

        print("\n" + "=" * 70)
        sys.exit(0)

    # Parse TTS backend
    tts_backend = TtsBackend.from_string(args.tts_backend)

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Validate mode-specific requirements
    if args.mode in ["populate-only", "regenerate"] and not args.language:
        print(f"Error: --language is required for --mode {args.mode}")
        sys.exit(1)

    # Validate language is supported by the selected backend
    if args.language and args.language not in BACKEND_LANGUAGES.get(tts_backend, []):
        print(
            f"Error: Language '{args.language}' is not supported by backend '{tts_backend.value}'"
        )
        print(f"Supported languages for {tts_backend.value}: {BACKEND_LANGUAGES[tts_backend]}")
        sys.exit(1)

    # Create agent with config
    agent = StrazdasAgent(
        config=config,
        output_dir=args.output_dir,
        upload_s3=args.upload_s3,
        tts_backend=tts_backend,
    )

    # Convert voice names to appropriate voice enum based on backend
    selected_voices: Optional[List[VoiceType]] = None
    if args.voices:
        try:
            if tts_backend == TtsBackend.ESPEAK:
                selected_voices = [EspeakVoice[v.upper()] for v in args.voices]
            elif tts_backend == TtsBackend.QWEN:
                selected_voices = [QwenVoice[v.upper()] for v in args.voices]
        except KeyError as e:
            print(f"Error: Unknown voice name for {tts_backend.value} backend: {e}")
            print("Use --list-voices to see available voices")
            sys.exit(1)

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
                coverage_results = query.all()
                print(f"\nLanguage: {args.language}")
                for voice_name, count in coverage_results:
                    print(f"  {voice_name}: {count} audio files")
            else:
                query = session.query(
                    AudioQualityReview.language_code,
                    AudioQualityReview.voice_name,
                    func.count(AudioQualityReview.id),
                ).group_by(AudioQualityReview.language_code, AudioQualityReview.voice_name)
                coverage_results = query.all()
                current_lang = None
                for lang_code, voice_name, count in coverage_results:
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

        # Confirm before running (unless --yes was provided)
        if not args.yes and not args.dry_run:
            # Count lemmas with translations
            session = agent.get_session()
            try:
                lemmas_with_translation = []
                if lemmas:
                    for lemma in lemmas:
                        if agent.get_translation_text(session, lemma, args.language):
                            lemmas_with_translation.append(lemma)
                lemma_count = len(lemmas_with_translation)
            finally:
                session.close()

            # Get default voices for the selected backend
            backend_voices = BACKEND_DEFAULT_VOICES.get(tts_backend, {})
            voice_list = selected_voices or backend_voices.get(args.language, [])
            voice_count = len(voice_list)
            estimated_files = lemma_count * voice_count

            voices_str = (
                ", ".join(v.name for v in selected_voices)
                if selected_voices
                else ", ".join(v.name for v in voice_list)
            )

            backend_desc = {
                TtsBackend.ESPEAK: "eSpeak-NG TTS (fast, local)",
                TtsBackend.QWEN: "Qwen3-TTS neural TTS (high quality, local)",
            }.get(tts_backend, tts_backend.value)

            if not confirm_operation(
                message=f"This will generate audio for {lemma_count} lemmas with {voice_count} voices each.\nTotal files: {estimated_files}\nVoices: {voices_str}\nBackend: {backend_desc}",
                estimated_calls=None,  # No API calls, local generation
                skip_confirmation=args.yes,
                dry_run=args.dry_run,
            ):
                print("Aborted.")
                sys.exit(0)

        # Run batch generation
        start_time = datetime.now()
        batch_results = agent.generate_batch(
            language_code=args.language,
            lemmas=lemmas,
            voices=selected_voices,
            use_ipa=args.use_ipa,
        )
        duration = (datetime.now() - start_time).total_seconds()

        # Print summary
        logger.info("=" * 80)
        logger.info(f"STRAZDAS AGENT REPORT - {tts_backend.value.upper()} Audio Generation")
        logger.info("=" * 80)
        logger.info(f"Backend: {tts_backend.value}")
        logger.info(f"Language: {batch_results['language_code']}")
        logger.info(f"Total lemmas: {batch_results['total_lemmas']}")
        logger.info(f"Voices: {', '.join(batch_results['voices'])}")
        logger.info(f"Successful: {batch_results['success_count']}")
        logger.info(f"Errors: {batch_results['error_count']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Output directory: {batch_results['output_dir']}")
        logger.info("=" * 80)


if __name__ == "__main__":
    main()
