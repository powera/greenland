#!/usr/bin/python3
"""Piper neural text-to-speech audio generation."""

from typing import Any

from .types import DEFAULT_PIPER_VOICES, RECOMMENDED_VOICES, PiperVoice

__all__ = [
    "PiperClient",
    "generate_audio",
    "PiperVoice",
    "DEFAULT_PIPER_VOICES",
    "RECOMMENDED_VOICES",
]


def __getattr__(name: str) -> Any:
    """Lazily import Piper runtime modules only when needed."""
    if name in {"PiperClient", "generate_audio"}:
        from .piper_tts import PiperClient, generate_audio

        exports = {
            "PiperClient": PiperClient,
            "generate_audio": generate_audio,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
