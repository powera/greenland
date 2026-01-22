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
from audioshoe.espeak import EspeakVoice
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
