#!/usr/bin/python3
"""Piper neural text-to-speech audio generation."""

from .piper_tts import PiperClient, generate_audio
from .types import (
    PiperVoice,
    DEFAULT_PIPER_VOICES,
    RECOMMENDED_VOICES,
)

__all__ = [
    "PiperClient",
    "generate_audio",
    "PiperVoice",
    "DEFAULT_PIPER_VOICES",
    "RECOMMENDED_VOICES",
]
