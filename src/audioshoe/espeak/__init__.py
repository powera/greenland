#!/usr/bin/python3
"""eSpeak-NG text-to-speech audio generation."""

from .espeak_tts import EspeakNGClient, generate_audio

__all__ = [
    "EspeakNGClient",
    "generate_audio",
]
