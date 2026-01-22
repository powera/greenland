#!/usr/bin/python3
"""Qwen3-TTS neural text-to-speech audio generation."""

from .qwen_tts import QwenTTSClient, generate_audio
from .types import (
    DEFAULT_QWEN_VOICES,
    QWEN_LANGUAGE_NAMES,
    RECOMMENDED_VOICES,
    SUPPORTED_LANGUAGES,
    VOICE_DESIGN_PROMPTS,
    QwenVoice,
)

__all__ = [
    "QwenTTSClient",
    "generate_audio",
    "QwenVoice",
    "DEFAULT_QWEN_VOICES",
    "RECOMMENDED_VOICES",
    "QWEN_LANGUAGE_NAMES",
    "SUPPORTED_LANGUAGES",
    "VOICE_DESIGN_PROMPTS",
]
