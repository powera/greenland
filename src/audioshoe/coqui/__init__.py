#!/usr/bin/python3
"""Coqui neural text-to-speech audio generation."""

from .coqui_tts import CoquiClient, generate_audio
from .types import DEFAULT_COQUI_VOICES, RECOMMENDED_VOICES, CoquiVoice

__all__ = [
    "CoquiClient",
    "generate_audio",
    "CoquiVoice",
    "DEFAULT_COQUI_VOICES",
    "RECOMMENDED_VOICES",
]
