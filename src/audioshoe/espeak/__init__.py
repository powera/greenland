#!/usr/bin/python3
"""eSpeak-NG text-to-speech audio generation."""

from .espeak_tts import EspeakNGClient, generate_audio
from .types import EspeakVoice, DEFAULT_ESPEAK_VOICES

__all__ = [
    "EspeakNGClient",
    "generate_audio",
    "EspeakVoice",
    "DEFAULT_ESPEAK_VOICES",
]
