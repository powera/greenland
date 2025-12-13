#!/usr/bin/python3
"""Coqui neural text-to-speech audio generation."""

from .coqui_tts import CoquiClient, generate_audio
from .types import (
    CoquiVoice,
    DEFAULT_COQUI_VOICES,
    RECOMMENDED_VOICES,
)

__all__ = [
    "CoquiClient",
    "generate_audio",
    "CoquiVoice",
    "DEFAULT_COQUI_VOICES",
    "RECOMMENDED_VOICES",
]
