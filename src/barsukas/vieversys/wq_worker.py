"""Workqueue handler for audio generation tasks.

This module implements the handle_generate_audio function that is called by
the Barsukas task worker when processing GENERATE_AUDIO tasks.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from flask import current_app
from sqlalchemy.orm import Session

from agents.common.wq_tools import build_default_config, get_lemma_or_raise
from config import Config
import constants
from agents.strazdas import StrazdasAgent, TtsBackend
from agents.vieversys import VieversysAgent
from audioshoe.coqui import CoquiVoice
from audioshoe.espeak import EspeakVoice
from audioshoe.piper import PiperVoice
from audioshoe.qwen import QwenVoice
from clients.audio import Voice
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def _get_audio_output_dir() -> str:
    """Get the audio output directory from config or use a temp directory."""
    # Try to get from Flask app config if we're in an app context
    try:
        audio_base_dir = current_app.config.get("AUDIO_BASE_DIR")
        if audio_base_dir:
            return audio_base_dir  # type: ignore[no-any-return]
    except RuntimeError:
        # Not in Flask app context (running from task worker)
        pass

    # Fall back to Config or environment variable
    audio_base_dir = getattr(Config, "AUDIO_BASE_DIR", None)
    if audio_base_dir:
        return audio_base_dir  # type: ignore[no-any-return]

    # Last resort: temp directory
    return tempfile.mkdtemp(prefix="audio_gen_")


def handle_generate_audio(session: Session, payload: Dict) -> str:
    """
    Handle audio generation task.

    Payload schema:
        lemma_id: int - ID of the lemma to generate audio for
        language_code: str - Target language code (e.g., "lt", "zh")
        voices: List[str] - Voice names to use (e.g., ["ash", "alloy", "nova"])
        tts_engine: str - TTS engine to use ("openai" or "espeak-ng")
        use_ipa: bool - Whether to use IPA for eSpeak-NG (optional, default False)

    Returns:
        str: Result message describing what was generated
    """
    lemma_id = payload["lemma_id"]
    language_code = payload["language_code"]
    voice_names = payload.get("voices", ["ash", "alloy", "nova"])
    tts_engine = payload.get("tts_engine", "openai")
    use_ipa = payload.get("use_ipa", False)

    lemma = get_lemma_or_raise(session, lemma_id)

    config = build_default_config()
    audio_output_dir = _get_audio_output_dir()

    # Convert voice names to appropriate enums based on TTS engine
    if tts_engine == "espeak-ng":
        espeak_voice_enums = [EspeakVoice[v.upper()] for v in voice_names]
        strazdas_agent = StrazdasAgent(
            config=config, output_dir=audio_output_dir, tts_backend=TtsBackend.ESPEAK
        )
        result = strazdas_agent.generate_audio_for_lemma(
            session,
            lemma,
            language_code,
            espeak_voice_enums,
            create_review_record=True,
            use_ipa=use_ipa,
        )
    elif tts_engine == "qwen3":
        qwen_voice_enums = [QwenVoice[v.upper()] for v in voice_names]
        strazdas_agent = StrazdasAgent(
            config=config, output_dir=audio_output_dir, tts_backend=TtsBackend.QWEN
        )
        result = strazdas_agent.generate_audio_for_lemma(
            session,
            lemma,
            language_code,
            qwen_voice_enums,
            create_review_record=True,
        )
    elif tts_engine == "piper":
        piper_voice_enums = [PiperVoice[v.upper()] for v in voice_names]
        result = _generate_audio_piper(
            session, lemma, language_code, piper_voice_enums, audio_output_dir
        )
    elif tts_engine == "coqui":
        coqui_voice_enums = [CoquiVoice[v.upper()] for v in voice_names]
        result = _generate_audio_coqui(
            session, lemma, language_code, coqui_voice_enums, audio_output_dir
        )
    else:
        # Default to OpenAI
        openai_voice_enums = [Voice(v) for v in voice_names]
        vieversys_agent = VieversysAgent(config=config, output_dir=audio_output_dir)
        result = vieversys_agent.generate_audio_for_lemma(
            session,
            lemma,
            language_code,
            openai_voice_enums,
            create_review_record=True,
        )

    if not result["success"]:
        raise RuntimeError(result.get("error", "Audio generation failed"))

    # Count successful voices
    successful_voices = [v for v in result.get("voices", []) if v.get("success")]
    voice_count = len(successful_voices)

    if voice_count == 0:
        raise RuntimeError("No audio files were generated successfully")

    return f"Generated audio for {voice_count} voice(s) in {language_code}"


def _generate_audio_piper(
    session: Session,
    lemma: Lemma,
    language_code: str,
    voices: List[PiperVoice],
    output_dir: str,
) -> Dict:
    """
    Generate audio for a lemma using Piper TTS.

    Args:
        session: Database session
        lemma: Lemma object
        language_code: Language code (e.g., "lt", "zh")
        voices: List of PiperVoice enums
        output_dir: Base output directory

    Returns:
        dict with success, voices (list of dicts with success key), and error information
    """
    import hashlib
    import json

    from audioshoe.piper import PiperClient
    from clients.audio.types import AudioFormat
    from wordfreq.storage.models.schema import AudioQualityReview
    from wordfreq.storage.translation_helpers import get_translation

    try:
        # Get translation for the language
        translation = get_translation(session, lemma, language_code)
        if not translation:
            return {
                "success": False,
                "error": f"No translation found for language: {language_code}",
                "voices": [],
            }

        # Create Piper client
        client = PiperClient()

        # Generate audio for each voice
        generated_voices = []
        for voice in voices:
            try:
                # Generate audio
                result = client.generate_audio(
                    text=translation,
                    voice=voice,
                    audio_format=AudioFormat.MP3,
                    speed=1.0,
                )

                if not result.success:
                    logger.error(f"Failed to generate audio for {voice.ui_name}: {result.error}")
                    generated_voices.append(
                        {"voice": voice.ui_name, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice.ui_name
                voice_dir.mkdir(parents=True, exist_ok=True)

                # Calculate MD5 hash
                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record
                review = AudioQualityReview(
                    guid=lemma.guid,
                    lemma_id=lemma.id,
                    language_code=language_code,
                    voice_name=voice.ui_name,
                    filename=filename,
                    expected_text=translation,
                    manifest_md5=md5_hash,
                    status="pending_review",
                    quality_issues=json.dumps([]),
                )
                session.add(review)
                generated_voices.append({"voice": voice.ui_name, "success": True})
            except Exception as e:
                logger.error(f"Error generating Piper audio for {voice.ui_name}: {e}")
                generated_voices.append({"voice": voice.ui_name, "success": False, "error": str(e)})

        session.commit()

        return {
            "success": True,
            "voices": generated_voices,
        }

    except Exception as e:
        logger.error(f"Error generating Piper audio: {e}")
        return {"success": False, "error": str(e), "voices": []}


def _generate_audio_coqui(
    session: Session,
    lemma: Lemma,
    language_code: str,
    voices: List[CoquiVoice],
    output_dir: str,
) -> Dict:
    """
    Generate audio for a lemma using Coqui TTS.

    Args:
        session: Database session
        lemma: Lemma object
        language_code: Language code (e.g., "lt", "zh")
        voices: List of CoquiVoice enums
        output_dir: Base output directory

    Returns:
        dict with success, voices (list of dicts with success key), and error information
    """
    import hashlib
    import json

    from audioshoe.coqui import CoquiClient
    from clients.audio.types import AudioFormat
    from wordfreq.storage.models.schema import AudioQualityReview
    from wordfreq.storage.translation_helpers import get_translation

    try:
        # Get translation for the language
        translation = get_translation(session, lemma, language_code)
        if not translation:
            return {
                "success": False,
                "error": f"No translation found for language: {language_code}",
                "voices": [],
            }

        # Create Coqui client
        client = CoquiClient()

        # Generate audio for each voice
        generated_voices = []
        for voice in voices:
            try:
                # Generate audio
                result = client.generate_audio(
                    text=translation,
                    voice=voice,
                    audio_format=AudioFormat.MP3,
                    speed=1.0,
                )

                if not result.success:
                    logger.error(f"Failed to generate audio for {voice.ui_name}: {result.error}")
                    generated_voices.append(
                        {"voice": voice.ui_name, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice.ui_name
                voice_dir.mkdir(parents=True, exist_ok=True)

                # Calculate MD5 hash
                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record
                review = AudioQualityReview(
                    guid=lemma.guid,
                    lemma_id=lemma.id,
                    language_code=language_code,
                    voice_name=voice.ui_name,
                    filename=filename,
                    expected_text=translation,
                    manifest_md5=md5_hash,
                    status="pending_review",
                    quality_issues=json.dumps([]),
                )
                session.add(review)
                generated_voices.append({"voice": voice.ui_name, "success": True})
            except Exception as e:
                logger.error(f"Error generating Coqui audio for {voice.ui_name}: {e}")
                generated_voices.append({"voice": voice.ui_name, "success": False, "error": str(e)})

        session.commit()

        return {
            "success": True,
            "voices": generated_voices,
        }

    except Exception as e:
        logger.error(f"Error generating Coqui audio: {e}")
        return {"success": False, "error": str(e), "voices": []}
