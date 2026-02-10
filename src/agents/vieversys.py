#!/usr/bin/env python3
"""
Vieversys - LLM API Audio Generation

This agent generates audio files for lemmas using cloud TTS APIs.
Supported engines: OpenAI TTS, Amazon Polly, Azure Cognitive TTS,
and Google Cloud Text-to-Speech.

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
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy import func
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
    add_level_args,
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
from clients.audio import AudioFormat, AudioGenerationResult, Voice, generate_audio
from clients.audio.azure_tts import AzureTTSClient, AzureVoice
from clients.audio.google_tts import GoogleTTSClient, GoogleTtsVoice
from clients.audio.gpt_voices import (
    DEFAULT_GPT_VOICES,
    GptVoice,
    get_character_description,
)
from clients.audio.polly_tts import PollyTTSClient, PollyVoice
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


class VieversysAgent:
    """Agent for generating audio files for lemmas using cloud TTS APIs."""

    def __init__(
        self,
        config: DataSourceConfig,
        output_dir: Optional[str] = None,
        upload_s3: bool = False,
        auto_approve: bool = False,
        skip_existing: bool = False,
        tts_engine: str = "openai",
    ) -> None:
        """
        Initialize the Vieversys agent.

        Args:
            config: DataSourceConfig with model, debug, and backend settings (required)
            output_dir: Output directory for generated audio (uses temp dir if None)
            upload_s3: Whether to upload generated audio to S3 staging
            auto_approve: Whether to automatically approve audio (requires upload_s3)
            skip_existing: Whether to skip lemma/voice combinations that already have audio
            tts_engine: TTS engine to use ('openai', 'polly', 'azure', 'google')
        """
        self.config = config
        self.debug = config.debug
        self.upload_s3 = upload_s3
        self.auto_approve = auto_approve
        self.skip_existing = skip_existing
        self.tts_engine = tts_engine
        self.output_dir = (
            Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="vieversys_"))
        )

        # Auto-approve requires S3 upload
        if self.auto_approve and not self.upload_s3:
            raise ValueError("--auto-approve requires --upload-s3")

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

    def _upload_to_staging_path(
        self,
        audio_path: Path,
        manifest_data: Dict[str, Any],
        md5_hash: str,
        language_code: str,
        voice_path_name: str,
    ) -> Tuple[bool, str, str]:
        """
        Upload audio and manifest to staging: staging/{language}/{voice}/{md5}.mp3

        Args:
            audio_path: Path to local audio file
            manifest_data: Manifest data dictionary
            md5_hash: MD5 hash of the audio file
            language_code: Language code (e.g., "lt", "zh")
            voice_path_name: Voice path name (e.g., "ruta", "jonas")

        Returns:
            Tuple of (success: bool, audio_url: str, manifest_url: str)
        """
        from clients.audio.s3_uploader import get_staging_audio_key, get_staging_manifest_key

        if not self.s3_uploader:
            return False, "", ""

        audio_key = get_staging_audio_key(language_code, voice_path_name, md5_hash)
        manifest_key = get_staging_manifest_key(language_code, voice_path_name, md5_hash)

        try:
            # Check if audio file already exists
            try:
                self.s3_uploader.s3.head_object(Bucket=self.s3_uploader.bucket_name, Key=audio_key)
                # File exists
                audio_url = self.s3_uploader.get_cdn_url(audio_key)
                manifest_url = self.s3_uploader.get_cdn_url(manifest_key)
                logger.info(f"Audio already exists in staging: {audio_key}")
                return True, audio_url, manifest_url
            except Exception:
                pass  # File doesn't exist, proceed with upload

            # Upload audio file
            audio_extra_args = {
                "ContentType": "audio/mpeg",
                "ACL": "public-read",
                "CacheControl": "public, max-age=3600",  # 1 hour cache for staging
            }
            self.s3_uploader.s3.upload_file(
                str(audio_path),
                self.s3_uploader.bucket_name,
                audio_key,
                ExtraArgs=audio_extra_args,
            )
            logger.info(f"Uploaded audio to staging: {audio_key}")

            # Upload manifest file
            import json

            manifest_json = json.dumps(manifest_data, indent=2, ensure_ascii=False)
            manifest_extra_args = {
                "ContentType": "application/json",
                "ACL": "public-read",
                "CacheControl": "public, max-age=3600",
            }
            self.s3_uploader.s3.put_object(
                Bucket=self.s3_uploader.bucket_name,
                Key=manifest_key,
                Body=manifest_json.encode("utf-8"),
                **manifest_extra_args,
            )
            logger.info(f"Uploaded manifest to staging: {manifest_key}")

            audio_url = self.s3_uploader.get_cdn_url(audio_key)
            manifest_url = self.s3_uploader.get_cdn_url(manifest_key)
            return True, audio_url, manifest_url

        except Exception as e:
            logger.error(f"Error uploading to staging: {e}")
            return False, "", ""

    def _upload_to_prod_path(
        self,
        audio_path: Path,
        md5_hash: str,
        language_code: str,
        voice_path_name: str,
    ) -> Tuple[bool, str]:
        """
        Upload audio file to production path: prod/{language}/{voice}/{md5}.mp3

        Args:
            audio_path: Path to local audio file
            md5_hash: MD5 hash of the audio file
            language_code: Language code (e.g., "lt", "zh")
            voice_path_name: Voice path name (e.g., "ruta", "jonas")

        Returns:
            Tuple of (success: bool, prod_url: str)
        """
        if not self.s3_uploader:
            return False, ""

        prod_key = f"prod/{language_code}/{voice_path_name}/{md5_hash}.mp3"

        try:
            # Check if file already exists
            try:
                self.s3_uploader.s3.head_object(Bucket=self.s3_uploader.bucket_name, Key=prod_key)
                # File exists
                prod_url = self.s3_uploader.get_cdn_url(prod_key)
                logger.info(f"Audio already exists in production: {prod_key}")
                return True, prod_url
            except Exception:
                pass  # File doesn't exist, proceed with upload

            # Upload to production
            extra_args = {
                "ContentType": "audio/mpeg",
                "ACL": "public-read",
                "CacheControl": "public, max-age=31536000, immutable",
            }
            self.s3_uploader.s3.upload_file(
                str(audio_path),
                self.s3_uploader.bucket_name,
                prod_key,
                ExtraArgs=extra_args,
            )

            prod_url = self.s3_uploader.get_cdn_url(prod_key)
            logger.info(f"Uploaded to production: {prod_key}")
            return True, prod_url

        except Exception as e:
            logger.error(f"Error uploading to production: {e}")
            return False, ""

    def generate_audio_for_lemma(
        self,
        session: Session,
        lemma: Lemma,
        language_code: str,
        voices: Sequence[GptVoice],
        create_review_record: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate audio files for a lemma in a specific language with multiple voices.

        Args:
            session: Database session
            lemma: Lemma to generate audio for
            language_code: Target language code
            voices: List of GptVoice to use
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

        voices_list: List[Dict[str, Any]] = []
        results: Dict[str, Any] = {
            "success": True,
            "lemma_guid": lemma.guid,
            "language": language_code,
            "text": text,
            "voices": voices_list,
        }

        for gpt_voice in voices:
            # Check if audio already exists for this lemma/language/voice combination
            if self.skip_existing:
                existing = (
                    session.query(AudioQualityReview)
                    .filter_by(
                        guid=lemma.guid,
                        language_code=language_code,
                        voice_name=gpt_voice.path_name,
                    )
                    .first()
                )
                if existing:
                    logger.info(
                        f"Skipping {lemma.guid}/{language_code}/{gpt_voice.path_name} - audio already exists"
                    )
                    voices_list.append(
                        {
                            "voice": gpt_voice.path_name,
                            "success": True,
                            "skipped": True,
                            "reason": "audio already exists",
                        }
                    )
                    continue

            # Get character description for this voice
            character_description = get_character_description(gpt_voice)
            logger.info(f"Generating audio: {text} ({language_code}/{gpt_voice.path_name})")

            # Generate audio using the underlying OpenAI voice
            result = generate_audio(
                text=text,
                voice=gpt_voice.openai_voice,
                language_code=language_code,
                character_description=character_description,
            )

            if not result.success:
                logger.error(f"Failed to generate audio: {result.error}")
                voices_list.append(
                    {
                        "voice": gpt_voice.path_name,
                        "success": False,
                        "error": result.error,
                    }
                )
                continue

            # Create filename and save
            # Use sanitized text for filename (simple version - just lowercase and replace spaces)
            safe_text = text.lower().replace(" ", "_")[:50]  # Limit length
            filename = f"{lemma.guid}_{safe_text}.mp3"

            # Create language/voice subdirectories using path_name (e.g., "ruta", "jonas")
            voice_dir = self.output_dir / language_code / gpt_voice.path_name
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
            s3_prod_url = None
            voice_path_name = gpt_voice.path_name
            if self.upload_s3 and self.s3_uploader:
                # Generate manifest
                manifest_data = generate_manifest(
                    audio_file_path=file_path,
                    agent="vieversys",
                    voice_name=voice_path_name,
                    language_code=language_code,
                    expected_text=text,
                    guid=lemma.guid,
                    sentence_id=None,
                    grammatical_form=None,
                    generation_params={
                        "model": result.model,
                        "openai_voice": gpt_voice.openai_voice_name,
                        "character": voice_path_name,
                    },
                )

                # Upload to staging: staging/{language}/{voice}/{md5}.mp3
                success, audio_url, manifest_url = self._upload_to_staging_path(
                    audio_path=file_path,
                    manifest_data=manifest_data,
                    md5_hash=md5_hash,
                    language_code=language_code,
                    voice_path_name=voice_path_name,
                )

                if success:
                    s3_staging_url = audio_url
                    s3_staging_manifest_url = manifest_url

                    # If auto-approve, also upload to production
                    # Production path: prod/{language}/{voice_path_name}/{md5}.mp3
                    if self.auto_approve:
                        prod_success, prod_url = self._upload_to_prod_path(
                            file_path, md5_hash, language_code, voice_path_name
                        )
                        if prod_success:
                            s3_prod_url = prod_url
                            logger.info(f"Auto-approved to S3 prod: {prod_url}")
                        else:
                            logger.error(f"Failed to upload to S3 prod: {file_path}")
                else:
                    logger.error(f"Failed to upload to S3 staging: {file_path}")

            # Create review record if requested
            if create_review_record:
                self._create_review_record(
                    session,
                    lemma,
                    language_code,
                    voice_path_name,
                    filename,
                    text,
                    md5_hash,
                    s3_staging_url=s3_staging_url,
                    s3_staging_manifest_url=s3_staging_manifest_url,
                    s3_prod_url=s3_prod_url,
                )

            voices_list.append(
                {
                    "voice": voice_path_name,
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
        session: Session,
        lemma: Lemma,
        language_code: str,
        voice_name: str,
        filename: str,
        text: str,
        md5_hash: str,
        s3_staging_url: Optional[str] = None,
        s3_staging_manifest_url: Optional[str] = None,
        s3_prod_url: Optional[str] = None,
    ) -> None:
        """Create AudioQualityReview record for generated audio."""
        # Determine status based on auto_approve setting
        status = "approved" if self.auto_approve else "pending_review"
        accepted_at = datetime.now() if self.auto_approve else None
        accepted_by = "vieversys-auto" if self.auto_approve else None

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
            existing.status = status
            existing.s3_staging_url = s3_staging_url
            existing.s3_staging_manifest_url = s3_staging_manifest_url
            existing.staging_agent = "vieversys" if s3_staging_url else None
            existing.s3_prod_url = s3_prod_url
            existing.accepted_at = accepted_at
            existing.accepted_by = accepted_by
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
                s3_prod_url=s3_prod_url,
                staging_agent="vieversys" if s3_staging_url else None,
                lemma_id=lemma.id,
                status=status,
                accepted_at=accepted_at,
                accepted_by=accepted_by,
            )
            session.add(review)
            logger.debug(f"Created review record for {lemma.guid}")

        session.commit()

    def generate_audio_for_sentence(
        self,
        session: Session,
        sentence: Sentence,
        sentence_translation: SentenceTranslation,
        voices: List[GptVoice],
        create_review_record: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate audio files for a sentence in a specific language with multiple voices.

        Args:
            session: Database session
            sentence: Sentence to generate audio for
            sentence_translation: SentenceTranslation with the text to speak
            voices: List of GptVoice to use
            create_review_record: Whether to create AudioQualityReview records

        Returns:
            Dict with generation results
        """
        text = sentence_translation.translation_text
        language_code = sentence_translation.language_code

        sent_voices_list: List[Dict[str, Any]] = []
        results: Dict[str, Any] = {
            "success": True,
            "sentence_id": sentence.id,
            "language": language_code,
            "text": text,
            "voices": sent_voices_list,
        }

        for gpt_voice in voices:
            # Check if audio already exists for this sentence/language/voice combination
            if self.skip_existing:
                existing = (
                    session.query(AudioQualityReview)
                    .filter_by(
                        sentence_id=sentence.id,
                        language_code=language_code,
                        voice_name=gpt_voice.path_name,
                    )
                    .first()
                )
                if existing:
                    logger.info(
                        f"Skipping sentence {sentence.id}/{language_code}/{gpt_voice.path_name} - audio already exists"
                    )
                    sent_voices_list.append(
                        {
                            "voice": gpt_voice.path_name,
                            "success": True,
                            "skipped": True,
                            "reason": "audio already exists",
                        }
                    )
                    continue

            character_description = get_character_description(gpt_voice)
            logger.info(f"Generating audio: {text} ({language_code}/{gpt_voice.path_name})")

            # Generate audio (with is_sentence=True for natural sentence pacing)
            result = generate_audio(
                text=text,
                voice=gpt_voice.openai_voice,
                language_code=language_code,
                is_sentence=True,
                character_description=character_description,
            )

            if not result.success:
                logger.error(f"Failed to generate audio: {result.error}")
                sent_voices_list.append(
                    {
                        "voice": gpt_voice.path_name,
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
            voice_path_name = gpt_voice.path_name
            voice_dir = self.output_dir / language_code / voice_path_name
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
                    voice_name=voice_path_name,
                    language_code=language_code,
                    expected_text=text,
                    guid=None,  # Sentences don't have GUIDs
                    sentence_id=sentence.id,
                    grammatical_form=None,
                    generation_params={
                        "model": result.model,
                        "openai_voice": gpt_voice.openai_voice_name,
                        "character": voice_path_name,
                    },
                )

                # Upload to staging: staging/{language}/{voice}/{md5}.mp3
                success, audio_url, manifest_url = self._upload_to_staging_path(
                    audio_path=file_path,
                    manifest_data=manifest_data,
                    md5_hash=md5_hash,
                    language_code=language_code,
                    voice_path_name=voice_path_name,
                )

                if success:
                    s3_staging_url = audio_url
                    s3_staging_manifest_url = manifest_url
                else:
                    logger.error(f"Failed to upload to S3 staging: {file_path}")

            # Create review record if requested
            if create_review_record:
                self._create_sentence_review_record(
                    session,
                    sentence,
                    language_code,
                    voice_path_name,
                    filename,
                    text,
                    md5_hash,
                    s3_staging_url=s3_staging_url,
                    s3_staging_manifest_url=s3_staging_manifest_url,
                )

            sent_voices_list.append(
                {
                    "voice": voice_path_name,
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
        session: Session,
        sentence: Sentence,
        language_code: str,
        voice_name: str,
        filename: str,
        text: str,
        md5_hash: str,
        s3_staging_url: Optional[str] = None,
        s3_staging_manifest_url: Optional[str] = None,
    ) -> None:
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

    def generate_audio_for_lemma_cloud(
        self,
        session: Session,
        lemma: Lemma,
        language_code: str,
        voice_names: List[str],
    ) -> Dict[str, Any]:
        """
        Generate audio for a lemma using a cloud TTS engine (Polly, Azure, or Google).

        Args:
            session: Database session
            lemma: Lemma to generate audio for
            language_code: Target language code
            voice_names: List of voice identifiers for the selected engine

        Returns:
            Dict with generation results
        """
        text = self.get_translation_text(session, lemma, language_code)
        if not text:
            logger.warning(f"No {language_code} translation for lemma {lemma.guid}")
            return {
                "success": False,
                "lemma_guid": lemma.guid,
                "language": language_code,
                "error": "No translation available",
            }

        results: Dict[str, Any] = {
            "success": True,
            "lemma_guid": lemma.guid,
            "language": language_code,
            "text": text,
            "voices": [],
        }

        for voice_name in voice_names:
            # Check if audio already exists
            if self.skip_existing:
                existing = (
                    session.query(AudioQualityReview)
                    .filter_by(
                        guid=lemma.guid,
                        language_code=language_code,
                        voice_name=voice_name,
                    )
                    .first()
                )
                if existing:
                    logger.info(
                        f"Skipping {lemma.guid}/{language_code}/{voice_name} - audio exists"
                    )
                    results["voices"].append(
                        {
                            "voice": voice_name,
                            "success": True,
                            "skipped": True,
                            "reason": "audio already exists",
                        }
                    )
                    continue

            logger.info(
                f"Generating audio ({self.tts_engine}): " f"{text} ({language_code}/{voice_name})"
            )

            # Generate audio with the selected engine
            result = self._call_cloud_tts(text, voice_name, language_code)

            if not result.success:
                logger.error(f"Failed to generate audio: {result.error}")
                results["voices"].append(
                    {"voice": voice_name, "success": False, "error": result.error}
                )
                continue

            # Save and process audio file
            safe_text = text.lower().replace(" ", "_")[:50]
            filename = f"{lemma.guid}_{safe_text}.mp3"

            voice_dir = self.output_dir / language_code / voice_name
            voice_dir.mkdir(parents=True, exist_ok=True)

            file_path = voice_dir / filename
            file_path.write_bytes(result.audio_data)

            md5_hash = hashlib.md5(result.audio_data).hexdigest()
            logger.info(f"Saved audio: {file_path} (MD5: {md5_hash})")

            # Upload to S3 staging if enabled
            s3_staging_url = None
            s3_staging_manifest_url = None
            s3_prod_url = None
            if self.upload_s3 and self.s3_uploader:
                manifest_data = generate_manifest(
                    audio_file_path=file_path,
                    agent="vieversys",
                    voice_name=voice_name,
                    language_code=language_code,
                    expected_text=text,
                    guid=lemma.guid,
                    sentence_id=None,
                    grammatical_form=None,
                    generation_params={
                        "model": result.model,
                        "engine": self.tts_engine,
                        "voice": voice_name,
                    },
                )

                success, audio_url, manifest_url = self._upload_to_staging_path(
                    audio_path=file_path,
                    manifest_data=manifest_data,
                    md5_hash=md5_hash,
                    language_code=language_code,
                    voice_path_name=voice_name,
                )

                if success:
                    s3_staging_url = audio_url
                    s3_staging_manifest_url = manifest_url
                    if self.auto_approve:
                        prod_success, prod_url = self._upload_to_prod_path(
                            file_path, md5_hash, language_code, voice_name
                        )
                        if prod_success:
                            s3_prod_url = prod_url

            # Create review record
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
                s3_prod_url=s3_prod_url,
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

    def _call_cloud_tts(
        self,
        text: str,
        voice_name: str,
        language_code: str,
    ) -> AudioGenerationResult:
        """Dispatch TTS call to the appropriate cloud engine.

        Args:
            text: Text to convert to speech
            voice_name: Voice identifier for the engine
            language_code: Language code

        Returns:
            AudioGenerationResult from the engine
        """
        if self.tts_engine == "polly":
            client = PollyTTSClient(debug=self.debug)
            # Find matching PollyVoice by name
            polly_voice = None
            for pv in PollyVoice:
                if pv.voice_id.lower() == voice_name.lower() or pv.ui_name == voice_name:
                    polly_voice = pv
                    break
            if not polly_voice:
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=language_code,
                    model="polly-neural",
                    duration_ms=0,
                    success=False,
                    error=f"Unknown Polly voice: {voice_name}",
                )
            return client.generate_audio(
                text=text,
                voice=polly_voice,
                language_code=language_code,
            )

        elif self.tts_engine == "azure":
            client_az = AzureTTSClient(debug=self.debug)
            azure_voice = None
            for av in AzureVoice:
                if (
                    av.voice_name.lower() == voice_name.lower()
                    or av.ui_name == voice_name
                    or av.name.lower() == voice_name.lower()
                ):
                    azure_voice = av
                    break
            if not azure_voice:
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=language_code,
                    model="azure-neural",
                    duration_ms=0,
                    success=False,
                    error=f"Unknown Azure voice: {voice_name}",
                )
            return client_az.generate_audio(
                text=text,
                voice=azure_voice,
                language_code=language_code,
            )

        elif self.tts_engine == "google":
            client_g = GoogleTTSClient(debug=self.debug)
            google_voice = None
            for gv in GoogleTtsVoice:
                if (
                    gv.voice_name.lower() == voice_name.lower()
                    or gv.ui_name == voice_name
                    or gv.name.lower() == voice_name.lower()
                ):
                    google_voice = gv
                    break
            if not google_voice:
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=language_code,
                    model="google-wavenet",
                    duration_ms=0,
                    success=False,
                    error=f"Unknown Google TTS voice: {voice_name}",
                )
            return client_g.generate_audio(
                text=text,
                voice=google_voice,
                language_code=language_code,
            )

        else:
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=language_code,
                model="unknown",
                duration_ms=0,
                success=False,
                error=f"Unknown TTS engine: {self.tts_engine}",
            )

    def generate_batch(
        self,
        language_code: str,
        lemmas: Optional[List[Lemma]] = None,
        voices: Optional[List[GptVoice]] = None,
        cloud_voice_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate audio for a batch of lemmas.

        Args:
            language_code: Target language code
            lemmas: List of lemmas to process (if None, returns empty result)
            voices: GptVoices to use for OpenAI engine (defaults to language's defaults)
            cloud_voice_names: Voice names for cloud engines (polly, azure, google)

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()
        use_cloud = self.tts_engine in ("polly", "azure", "google")

        if not use_cloud:
            voices = voices or DEFAULT_GPT_VOICES.get(
                language_code, GptVoice.get_default_voices_for_language(language_code)
            )

        try:
            # Determine voice display names for the result
            if use_cloud and cloud_voice_names:
                voice_display = cloud_voice_names
            elif voices:
                voice_display = [v.path_name for v in voices]
            else:
                voice_display = cloud_voice_names or []

            # If no lemmas provided, return empty result
            if not lemmas:
                return {
                    "language_code": language_code,
                    "total_lemmas": 0,
                    "voices": voice_display,
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

            logger.info(
                f"Generating audio ({self.tts_engine}) for "
                f"{len(lemmas)} lemmas in {language_code}"
            )

            results: Dict[str, Any] = {
                "language_code": language_code,
                "total_lemmas": len(lemmas),
                "voices": voice_display,
                "output_dir": str(self.output_dir),
                "lemmas": [],
                "success_count": 0,
                "error_count": 0,
            }

            for i, lemma in enumerate(lemmas, 1):
                logger.info(f"[{i}/{len(lemmas)}] Processing {lemma.guid}")

                if use_cloud and cloud_voice_names:
                    result = self.generate_audio_for_lemma_cloud(
                        session, lemma, language_code, cloud_voice_names
                    )
                else:
                    result = self.generate_audio_for_lemma(
                        session, lemma, language_code, voices or [], create_review_record=True
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
        voices: Optional[List[GptVoice]] = None,
    ) -> Dict[str, Any]:
        """
        Generate audio for sentences.

        Args:
            language_code: Target language code
            guid: Optional GUID to filter sentences by (sentences that use this lemma)
            limit: Maximum number of sentences to process per language (default: 10)
            voices: GptVoices to use (defaults to language's default voices)

        Returns:
            Dict with batch generation results
        """
        session = self.get_session()
        voices = voices or DEFAULT_GPT_VOICES.get(
            language_code, GptVoice.get_default_voices_for_language(language_code)
        )

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
                query = query.filter(Sentence.id.in_(sentence_ids_subquery))  # type: ignore[arg-type]

            # If skip_existing is enabled, filter out sentences that already have audio
            # for ALL of the specified voices
            if self.skip_existing:
                voice_names = [v.path_name for v in voices]
                # Find sentence IDs that have audio for all voices
                sentences_with_all_voices = (
                    session.query(AudioQualityReview.sentence_id)
                    .filter(
                        AudioQualityReview.sentence_id.isnot(None),
                        AudioQualityReview.language_code == language_code,
                        AudioQualityReview.voice_name.in_(voice_names),
                    )
                    .group_by(AudioQualityReview.sentence_id)
                    .having(
                        func.count(func.distinct(AudioQualityReview.voice_name)) == len(voice_names)
                    )
                    .subquery()
                )
                query = query.filter(Sentence.id.notin_(sentences_with_all_voices))  # type: ignore[arg-type]

            # Order by sentence ID and limit
            query = query.order_by(Sentence.id).limit(limit)

            sentence_pairs = query.all()

            if not sentence_pairs:
                return {
                    "language_code": language_code,
                    "guid": guid,
                    "total_sentences": 0,
                    "voices": [v.path_name for v in voices],
                    "output_dir": str(self.output_dir),
                    "sentences": [],
                    "success_count": 0,
                    "error_count": 0,
                }

            logger.info(f"Generating audio for {len(sentence_pairs)} sentences in {language_code}")

            results: Dict[str, Any] = {
                "language_code": language_code,
                "guid": guid,
                "total_sentences": len(sentence_pairs),
                "voices": [v.path_name for v in voices],
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

        manifest: Dict[str, Any] = {"language": language_code, "voice": voice_name, "files": {}}

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


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(description="Vieversys - LLM API Audio Generation")

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser)
    add_processing_args(parser)
    add_level_args(parser)
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
        choices=["lt", "zh", "es", "fr", "ko", "de", "pt", "sw", "vi"],
        help="Target language code (required for populate-only and regenerate modes)",
    )
    parser.add_argument(
        "--tts-engine",
        choices=["openai", "polly", "azure", "google"],
        default="openai",
        help="TTS engine to use: openai (default), polly (Amazon Polly), azure (Azure Cognitive), google (Google Cloud TTS)",
    )
    parser.add_argument(
        "--voices",
        nargs="+",
        help="Voice names to use. For OpenAI: character names (ruta, jonas). For cloud engines: voice IDs (e.g., Zhiyu, zh-CN-XiaoxiaoNeural, cmn-CN-Wavenet-A).",
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
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve generated audio (sets status to 'approved' and copies to prod)",
    )

    return parser


def _print_cloud_voices(engine: str) -> None:
    """Print available voice names for a cloud TTS engine."""
    print(f"\nAvailable {engine} voices:")
    languages: Dict[str, List[str]] = {}

    if engine == "polly":
        for pv in PollyVoice:
            languages.setdefault(pv.language_code, []).append(
                f"{pv.voice_id} ({pv.gender.upper()})"
            )
    elif engine == "azure":
        for av in AzureVoice:
            languages.setdefault(av.language_code, []).append(
                f"{av.voice_name} ({av.gender.upper()})"
            )
    elif engine == "google":
        for gv in GoogleTtsVoice:
            languages.setdefault(gv.language_code, []).append(
                f"{gv.voice_name} ({gv.gender.upper()})"
            )
    else:
        return

    for lang_code in sorted(languages.keys()):
        print(f"  {lang_code}: {', '.join(languages[lang_code])}")


def main() -> None:
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
    tts_engine = getattr(args, "tts_engine", "openai")
    agent = VieversysAgent(
        config=config,
        output_dir=args.output_dir,
        upload_s3=args.upload_s3,
        auto_approve=args.auto_approve,
        skip_existing=(args.mode == "populate-only"),
        tts_engine=tts_engine,
    )

    # Convert voice names based on TTS engine
    voices = None
    cloud_voice_names: Optional[List[str]] = None

    if tts_engine in ("polly", "azure", "google"):
        # For cloud engines, voice names are passed as-is
        if args.voices:
            cloud_voice_names = args.voices
        else:
            # Provide defaults for cloud engines
            lang = args.language or "es"
            if tts_engine == "polly":
                defaults = PollyVoice.get_voices_for_language(lang)
                cloud_voice_names = [v.voice_id for v in defaults] if defaults else []
            elif tts_engine == "azure":
                defaults_az = AzureVoice.get_voices_for_language(lang)
                cloud_voice_names = [v.name.lower() for v in defaults_az] if defaults_az else []
            elif tts_engine == "google":
                defaults_g = GoogleTtsVoice.get_voices_for_language(lang)
                cloud_voice_names = [v.name.lower() for v in defaults_g] if defaults_g else []

            if not cloud_voice_names:
                print(f"Error: No {tts_engine} voices available for language '{lang}'")
                _print_cloud_voices(tts_engine)
                sys.exit(1)
    elif args.voices:
        # OpenAI: match by path_name or ui_name
        voices = []
        for v in args.voices:
            gpt_voice = GptVoice.from_ui_name(v)
            if gpt_voice:
                voices.append(gpt_voice)
                continue
            found = False
            for voice in GptVoice:
                if voice.path_name == v.lower():
                    voices.append(voice)
                    found = True
                    break
            if not found:
                print(f"Error: Unknown voice '{v}'")
                print("Available voices by language:")
                for lang in ["lt", "zh", "es", "fr"]:
                    lang_voices = GptVoice.get_voices_for_language(lang)
                    names = [gv.path_name for gv in lang_voices]
                    print(f"  {lang}: {', '.join(names)}")
                sys.exit(1)

    # Get lemmas to process (either single lemma from --guid or batch)
    # Only needed for modes that process lemmas (not coverage, check-existing, or sentence generation)
    lemmas = None
    if args.mode in ["populate-only", "regenerate"] and not args.generate_sentences:
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
                lang_query = (
                    session.query(AudioQualityReview.voice_name, func.count(AudioQualityReview.id))
                    .filter(AudioQualityReview.language_code == args.language)
                    .group_by(AudioQualityReview.voice_name)
                )
                lang_results = lang_query.all()
                print(f"\nLanguage: {args.language}")
                for voice_name, count in lang_results:
                    print(f"  {voice_name}: {count} audio files")
            else:
                all_query = session.query(
                    AudioQualityReview.language_code,
                    AudioQualityReview.voice_name,
                    func.count(AudioQualityReview.id),
                ).group_by(AudioQualityReview.language_code, AudioQualityReview.voice_name)
                all_results = all_query.all()
                current_lang = None
                for lang_code, voice_name, count in all_results:
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
            existing_query = session.query(AudioQualityReview)

            if args.language:
                existing_query = existing_query.filter(
                    AudioQualityReview.language_code == args.language
                )

            if args.limit:
                existing_query = existing_query.limit(args.limit)

            audio_files = existing_query.all()

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
            voice_count = len(voices) if voices else len(DEFAULT_GPT_VOICES.get(args.language, []))
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
            batch_results = agent.generate_sentences_batch(
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
            logger.info(f"Language: {batch_results['language_code']}")
            if batch_results.get("guid"):
                logger.info(f"GUID: {batch_results['guid']}")
            logger.info(f"Total sentences: {batch_results['total_sentences']}")
            logger.info(f"Voices: {', '.join(batch_results['voices'])}")
            logger.info(f"Successful: {batch_results['success_count']}")
            logger.info(f"Errors: {batch_results['error_count']}")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info(f"Output directory: {batch_results['output_dir']}")
            logger.info("=" * 80)
            return

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

            if cloud_voice_names:
                voice_count = len(cloud_voice_names)
            elif voices:
                voice_count = len(voices)
            else:
                voice_count = len(DEFAULT_GPT_VOICES.get(args.language, []))
            estimated_calls = lemma_count * voice_count

            engine_label = tts_engine.title() if tts_engine != "openai" else "OpenAI"
            if not confirm_operation(
                message=f"This will generate audio for {lemma_count} lemmas with {voice_count} voices each.\nTotal API calls: {estimated_calls}\nThis will use {engine_label} TTS API and may incur costs.",
                estimated_calls=estimated_calls,
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
            voices=voices,
            cloud_voice_names=cloud_voice_names,
        )
        duration = (datetime.now() - start_time).total_seconds()

        # Generate manifests if requested
        if args.generate_manifests:
            logger.info("Generating manifests...")
            voice_list = voices or DEFAULT_GPT_VOICES.get(args.language, [])
            for voice in voice_list:
                try:
                    manifest_path = agent.generate_manifest(args.language, voice.path_name)
                    logger.info(f"Generated manifest: {manifest_path}")
                except Exception as e:
                    logger.error(f"Error generating manifest for {voice.path_name}: {e}")

        # Print summary
        logger.info("=" * 80)
        logger.info("VIEVERSYS AGENT REPORT - Audio Generation")
        logger.info("=" * 80)
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
