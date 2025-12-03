#!/usr/bin/python3
"""Type definitions for audio generation."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Voice(Enum):
    """Available OpenAI TTS voices."""
    ALLOY = "alloy"
    ASH = "ash"
    BALLAD = "ballad"
    CORAL = "coral"
    ECHO = "echo"
    FABLE = "fable"
    NOVA = "nova"
    ONYX = "onyx"
    SAGE = "sage"
    SHIMMER = "shimmer"


class AudioFormat(Enum):
    """Supported audio output formats."""
    MP3 = "mp3"
    OPUS = "opus"
    AAC = "aac"
    FLAC = "flac"
    WAV = "wav"
    PCM = "pcm"


@dataclass
class AudioGenerationResult:
    """Result of an audio generation request."""
    audio_data: bytes
    text: str
    voice: Voice
    language_code: str
    model: str
    duration_ms: float
    success: bool = True
    error: Optional[str] = None
