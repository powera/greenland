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

from workqueue.tools import build_default_config, get_lemma_or_raise
from barsukas.config import Config
import constants
from agents.strazdas import StrazdasAgent, TtsBackend
from agents.vieversys import VieversysAgent
from audioshoe.coqui import CoquiVoice
from audioshoe.espeak import EspeakVoice
from audioshoe.piper import PiperVoice
from audioshoe.qwen import QwenVoice
from clients.audio import Voice
from clients.audio.gpt_voices import GptVoice
from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma, Sentence, SentenceTranslation

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
    elif tts_engine in ("polly", "azure", "google"):
        # Cloud TTS engines dispatched through VieversysAgent
        vieversys_agent = VieversysAgent(
            config=config, output_dir=audio_output_dir, tts_engine=tts_engine
        )
        result = vieversys_agent.generate_audio_for_lemma_cloud(
            session,
            lemma,
            language_code,
            voice_names,
        )
    else:
        # Default to OpenAI - convert Voice names to GptVoice objects
        gpt_voice_list: List[GptVoice] = []
        invalid_voice_names: List[str] = []
        for v in voice_names:
            try:
                openai_voice = Voice(v)
            except ValueError:
                invalid_voice_names.append(v)
                continue
            gpt_voice = GptVoice.from_openai_voice(openai_voice, language_code)
            if gpt_voice is not None:
                gpt_voice_list.append(gpt_voice)

        if invalid_voice_names:
            raise RuntimeError(
                "Invalid OpenAI voice names: "
                + ", ".join(invalid_voice_names)
            )

        if not gpt_voice_list:
            supported_languages = sorted({voice.language_code for voice in GptVoice})
            raise RuntimeError(
                "OpenAI audio is not configured for language "
                f"'{language_code}'. Supported languages: {', '.join(supported_languages)}"
            )

        vieversys_agent = VieversysAgent(config=config, output_dir=audio_output_dir)
        result = vieversys_agent.generate_audio_for_lemma(
            session,
            lemma,
            language_code,
            gpt_voice_list,
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
    from storage.models.schema import AudioQualityReview
    from storage.translation_helpers import get_translation

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
    from storage.models.schema import AudioQualityReview
    from storage.translation_helpers import get_translation

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


def handle_generate_sentence_audio(session: Session, payload: Dict) -> str:
    """
    Handle audio generation task for sentences.

    Payload schema:
        sentence_id: int - ID of the sentence to generate audio for
        language_code: str - Target language code (e.g., "lt", "zh")
        voices: List[str] - Voice names to use (e.g., ["ash", "alloy", "nova"])
        tts_engine: str - TTS engine to use ("openai", "espeak-ng", "piper", "coqui", "qwen3")

    Returns:
        str: Result message describing what was generated
    """
    sentence_id = payload["sentence_id"]
    language_code = payload["language_code"]
    voice_names = payload.get("voices", ["ash", "alloy", "nova"])
    tts_engine = payload.get("tts_engine", "openai")

    # Get sentence
    sentence = session.query(Sentence).filter_by(id=sentence_id).first()
    if not sentence:
        raise ValueError(f"Sentence {sentence_id} not found")

    # Get translation
    translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code=language_code)
        .first()
    )
    if not translation:
        raise ValueError(f"No {language_code} translation for sentence {sentence_id}")

    text = translation.translation_text.strip()
    if not text:
        raise ValueError(f"Empty translation for sentence {sentence_id} in {language_code}")

    config = build_default_config()
    audio_output_dir = _get_audio_output_dir()

    # Generate audio based on TTS engine
    if tts_engine == "espeak-ng":
        result = _generate_sentence_audio_espeak(
            session, sentence_id, text, language_code, voice_names, audio_output_dir, config
        )
    elif tts_engine == "qwen3":
        result = _generate_sentence_audio_qwen(
            session, sentence_id, text, language_code, voice_names, audio_output_dir, config
        )
    elif tts_engine == "piper":
        result = _generate_sentence_audio_piper(
            session, sentence_id, text, language_code, voice_names, audio_output_dir
        )
    elif tts_engine == "coqui":
        result = _generate_sentence_audio_coqui(
            session, sentence_id, text, language_code, voice_names, audio_output_dir
        )
    elif tts_engine in ("polly", "azure", "google"):
        result = _generate_sentence_audio_cloud(
            session, sentence_id, text, language_code, voice_names, audio_output_dir, tts_engine
        )
    else:
        # Default to OpenAI
        result = _generate_sentence_audio_openai(
            session, sentence_id, text, language_code, voice_names, audio_output_dir
        )

    if not result["success"]:
        raise RuntimeError(result.get("error", "Sentence audio generation failed"))

    successful_voices = [v for v in result.get("voices", []) if v.get("success")]
    voice_count = len(successful_voices)

    if voice_count == 0:
        raise RuntimeError("No audio files were generated successfully for sentence")

    return f"Generated sentence audio for {voice_count} voice(s) in {language_code}"


def _generate_sentence_audio_openai(
    session: Session,
    sentence_id: int,
    text: str,
    language_code: str,
    voice_names: List[str],
    output_dir: str,
) -> Dict:
    """Generate sentence audio using OpenAI TTS."""
    import hashlib
    import json

    from clients.audio import generate_audio
    from clients.audio.types import AudioFormat
    from storage.models.schema import AudioQualityReview

    try:
        openai_voice_enums = [Voice(v) for v in voice_names]
        generated_voices = []

        for voice in openai_voice_enums:
            try:
                result = generate_audio(text=text, voice=voice, language_code=language_code)

                if not result.success:
                    logger.error(f"Failed to generate OpenAI audio for sentence: {result.error}")
                    generated_voices.append(
                        {"voice": voice.value, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice.value
                voice_dir.mkdir(parents=True, exist_ok=True)

                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record for sentence
                review = AudioQualityReview(
                    guid=f"S_{sentence_id:05d}",  # Synthetic GUID for sentences
                    sentence_id=sentence_id,
                    language_code=language_code,
                    voice_name=voice.value,
                    filename=filename,
                    expected_text=text,
                    manifest_md5=md5_hash,
                    status="pending_review",
                    quality_issues=json.dumps([]),
                )
                session.add(review)
                generated_voices.append({"voice": voice.value, "success": True})

            except Exception as e:
                logger.error(f"Error generating OpenAI audio for {voice.value}: {e}")
                generated_voices.append({"voice": voice.value, "success": False, "error": str(e)})

        session.commit()
        return {"success": True, "voices": generated_voices}

    except Exception as e:
        logger.error(f"Error generating OpenAI sentence audio: {e}")
        return {"success": False, "error": str(e), "voices": []}


def _generate_sentence_audio_espeak(
    session: Session,
    sentence_id: int,
    text: str,
    language_code: str,
    voice_names: List[str],
    output_dir: str,
    config: DataSourceConfig,
) -> Dict:
    """Generate sentence audio using eSpeak-NG."""
    import hashlib
    import json

    from audioshoe.espeak import EspeakNGClient
    from clients.audio.types import AudioFormat
    from storage.models.schema import AudioQualityReview

    try:
        espeak_voice_enums = [EspeakVoice[v.upper()] for v in voice_names]
        client = EspeakNGClient()

        generated_voices = []
        for voice in espeak_voice_enums:
            try:
                result = client.generate_audio(
                    text=text,
                    voice=voice,
                    audio_format=AudioFormat.MP3,
                )

                if not result.success:
                    logger.error(f"Failed to generate eSpeak audio: {result.error}")
                    generated_voices.append(
                        {"voice": voice.name, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice.name
                voice_dir.mkdir(parents=True, exist_ok=True)

                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record
                review = AudioQualityReview(
                    guid=f"S_{sentence_id:05d}",  # Synthetic GUID for sentences
                    sentence_id=sentence_id,
                    language_code=language_code,
                    voice_name=voice.name,
                    filename=filename,
                    expected_text=text,
                    manifest_md5=md5_hash,
                    status="pending_review",
                    quality_issues=json.dumps([]),
                )
                session.add(review)
                generated_voices.append({"voice": voice.name, "success": True})

            except Exception as e:
                logger.error(f"Error generating eSpeak audio for {voice.name}: {e}")
                generated_voices.append({"voice": voice.name, "success": False, "error": str(e)})

        session.commit()
        return {"success": True, "voices": generated_voices}

    except Exception as e:
        logger.error(f"Error generating eSpeak sentence audio: {e}")
        return {"success": False, "error": str(e), "voices": []}


def _generate_sentence_audio_qwen(
    session: Session,
    sentence_id: int,
    text: str,
    language_code: str,
    voice_names: List[str],
    output_dir: str,
    config: DataSourceConfig,
) -> Dict:
    """Generate sentence audio using Qwen3."""
    import hashlib
    import json

    from audioshoe.qwen import QwenTTSClient
    from clients.audio.types import AudioFormat
    from storage.models.schema import AudioQualityReview

    try:
        qwen_voice_enums = [QwenVoice[v.upper()] for v in voice_names]
        client = QwenTTSClient()

        generated_voices = []
        for voice in qwen_voice_enums:
            try:
                result = client.generate_audio(
                    text=text,
                    voice=voice,
                    audio_format=AudioFormat.MP3,
                )

                if not result.success:
                    logger.error(f"Failed to generate Qwen audio: {result.error}")
                    generated_voices.append(
                        {"voice": voice.ui_name, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice.ui_name
                voice_dir.mkdir(parents=True, exist_ok=True)

                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record
                review = AudioQualityReview(
                    guid=f"S_{sentence_id:05d}",  # Synthetic GUID for sentences
                    sentence_id=sentence_id,
                    language_code=language_code,
                    voice_name=voice.ui_name,
                    filename=filename,
                    expected_text=text,
                    manifest_md5=md5_hash,
                    status="pending_review",
                    quality_issues=json.dumps([]),
                )
                session.add(review)
                generated_voices.append({"voice": voice.ui_name, "success": True})

            except Exception as e:
                logger.error(f"Error generating Qwen audio for {voice.ui_name}: {e}")
                generated_voices.append({"voice": voice.ui_name, "success": False, "error": str(e)})

        session.commit()
        return {"success": True, "voices": generated_voices}

    except Exception as e:
        logger.error(f"Error generating Qwen sentence audio: {e}")
        return {"success": False, "error": str(e), "voices": []}


def _generate_sentence_audio_piper(
    session: Session,
    sentence_id: int,
    text: str,
    language_code: str,
    voice_names: List[str],
    output_dir: str,
) -> Dict:
    """Generate sentence audio using Piper TTS."""
    import hashlib
    import json

    from audioshoe.piper import PiperClient
    from clients.audio.types import AudioFormat
    from storage.models.schema import AudioQualityReview

    try:
        piper_voice_enums = [PiperVoice[v.upper()] for v in voice_names]
        client = PiperClient()

        generated_voices = []
        for voice in piper_voice_enums:
            try:
                result = client.generate_audio(
                    text=text,
                    voice=voice,
                    audio_format=AudioFormat.MP3,
                    speed=1.0,
                )

                if not result.success:
                    logger.error(f"Failed to generate Piper audio: {result.error}")
                    generated_voices.append(
                        {"voice": voice.ui_name, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice.ui_name
                voice_dir.mkdir(parents=True, exist_ok=True)

                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record
                review = AudioQualityReview(
                    guid=f"S_{sentence_id:05d}",  # Synthetic GUID for sentences
                    sentence_id=sentence_id,
                    language_code=language_code,
                    voice_name=voice.ui_name,
                    filename=filename,
                    expected_text=text,
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
        return {"success": True, "voices": generated_voices}

    except Exception as e:
        logger.error(f"Error generating Piper sentence audio: {e}")
        return {"success": False, "error": str(e), "voices": []}


def _generate_sentence_audio_coqui(
    session: Session,
    sentence_id: int,
    text: str,
    language_code: str,
    voice_names: List[str],
    output_dir: str,
) -> Dict:
    """Generate sentence audio using Coqui TTS."""
    import hashlib
    import json

    from audioshoe.coqui import CoquiClient
    from clients.audio.types import AudioFormat
    from storage.models.schema import AudioQualityReview

    try:
        coqui_voice_enums = [CoquiVoice[v.upper()] for v in voice_names]
        client = CoquiClient()

        generated_voices = []
        for voice in coqui_voice_enums:
            try:
                result = client.generate_audio(
                    text=text,
                    voice=voice,
                    audio_format=AudioFormat.MP3,
                    speed=1.0,
                )

                if not result.success:
                    logger.error(f"Failed to generate Coqui audio: {result.error}")
                    generated_voices.append(
                        {"voice": voice.ui_name, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice.ui_name
                voice_dir.mkdir(parents=True, exist_ok=True)

                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record
                review = AudioQualityReview(
                    guid=f"S_{sentence_id:05d}",  # Synthetic GUID for sentences
                    sentence_id=sentence_id,
                    language_code=language_code,
                    voice_name=voice.ui_name,
                    filename=filename,
                    expected_text=text,
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
        return {"success": True, "voices": generated_voices}

    except Exception as e:
        logger.error(f"Error generating Coqui sentence audio: {e}")
        return {"success": False, "error": str(e), "voices": []}


def _generate_sentence_audio_cloud(
    session: Session,
    sentence_id: int,
    text: str,
    language_code: str,
    voice_names: List[str],
    output_dir: str,
    tts_engine: str,
) -> Dict:
    """Generate sentence audio using a cloud TTS engine (Polly, Azure, or Google)."""
    import hashlib
    import json

    from clients.audio.azure_tts import AzureTTSClient, AzureVoice
    from clients.audio.google_tts import GoogleTTSClient, GoogleTtsVoice
    from clients.audio.polly_tts import PollyTTSClient, PollyVoice
    from clients.audio.types import AudioFormat
    from storage.models.schema import AudioQualityReview

    try:
        generated_voices: List[Dict] = []

        for voice_name in voice_names:
            try:
                # Generate audio with the appropriate cloud engine
                if tts_engine == "polly":
                    client_p = PollyTTSClient()
                    polly_voice = None
                    for pv in PollyVoice:
                        if pv.name.lower() == voice_name.lower() or pv.ui_name == voice_name:
                            polly_voice = pv
                            break
                    if not polly_voice:
                        generated_voices.append(
                            {
                                "voice": voice_name,
                                "success": False,
                                "error": f"Unknown voice: {voice_name}",
                            }
                        )
                        continue
                    result = client_p.generate_audio(
                        text=text, voice=polly_voice, language_code=language_code
                    )
                elif tts_engine == "azure":
                    client_a = AzureTTSClient()
                    azure_voice = None
                    for av in AzureVoice:
                        if av.name.lower() == voice_name.lower() or av.ui_name == voice_name:
                            azure_voice = av
                            break
                    if not azure_voice:
                        generated_voices.append(
                            {
                                "voice": voice_name,
                                "success": False,
                                "error": f"Unknown voice: {voice_name}",
                            }
                        )
                        continue
                    result = client_a.generate_audio(
                        text=text, voice=azure_voice, language_code=language_code
                    )
                elif tts_engine == "google":
                    client_g = GoogleTTSClient()
                    google_voice = None
                    for gv in GoogleTtsVoice:
                        if gv.name.lower() == voice_name.lower() or gv.ui_name == voice_name:
                            google_voice = gv
                            break
                    if not google_voice:
                        generated_voices.append(
                            {
                                "voice": voice_name,
                                "success": False,
                                "error": f"Unknown voice: {voice_name}",
                            }
                        )
                        continue
                    result = client_g.generate_audio(
                        text=text, voice=google_voice, language_code=language_code
                    )
                else:
                    generated_voices.append(
                        {
                            "voice": voice_name,
                            "success": False,
                            "error": f"Unknown engine: {tts_engine}",
                        }
                    )
                    continue

                if not result.success:
                    logger.error(f"Failed to generate {tts_engine} audio: {result.error}")
                    generated_voices.append(
                        {"voice": voice_name, "success": False, "error": result.error}
                    )
                    continue

                # Save audio file
                voice_dir = Path(output_dir) / language_code / voice_name
                voice_dir.mkdir(parents=True, exist_ok=True)

                md5_hash = hashlib.md5(result.audio_data).hexdigest()
                filename = f"{md5_hash}.mp3"
                file_path = voice_dir / filename

                with open(file_path, "wb") as f:
                    f.write(result.audio_data)

                # Create review record
                review = AudioQualityReview(
                    guid=f"S_{sentence_id:05d}",
                    sentence_id=sentence_id,
                    language_code=language_code,
                    voice_name=voice_name,
                    filename=filename,
                    expected_text=text,
                    manifest_md5=md5_hash,
                    status="pending_review",
                    quality_issues=json.dumps([]),
                )
                session.add(review)
                generated_voices.append({"voice": voice_name, "success": True})

            except Exception as e:
                logger.error(f"Error generating {tts_engine} audio for {voice_name}: {e}")
                generated_voices.append({"voice": voice_name, "success": False, "error": str(e)})

        session.commit()
        return {"success": True, "voices": generated_voices}

    except Exception as e:
        logger.error(f"Error generating {tts_engine} sentence audio: {e}")
        return {"success": False, "error": str(e), "voices": []}
