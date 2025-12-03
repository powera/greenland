#!/usr/bin/python3
"""Audio generation client API for OpenAI TTS."""

from .openai_tts import OpenAITTSClient, generate_audio
from .types import Voice, AudioFormat, AudioGenerationResult
from .s3_uploader import S3AudioUploader, upload_audio_file, get_uploader

__all__ = [
    "OpenAITTSClient",
    "generate_audio",
    "AudioGenerationResult",
    "Voice",
    "AudioFormat",
    "S3AudioUploader",
    "upload_audio_file",
    "get_uploader",
]
