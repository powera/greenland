#!/usr/bin/python3
"""Coqui neural text-to-speech audio generation."""

from typing import Any

from .types import DEFAULT_COQUI_VOICES, RECOMMENDED_VOICES, CoquiVoice

__all__ = [
    "CoquiClient",
    "generate_audio",
    "CoquiVoice",
    "DEFAULT_COQUI_VOICES",
    "RECOMMENDED_VOICES",
]


def __getattr__(name: str) -> Any:
    """Lazily import Coqui runtime modules only when needed."""
    if name in {"CoquiClient", "generate_audio"}:
        from .coqui_tts import CoquiClient, generate_audio

        exports = {
            "CoquiClient": CoquiClient,
            "generate_audio": generate_audio,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
