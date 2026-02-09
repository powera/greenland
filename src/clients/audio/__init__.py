#!/usr/bin/python3
"""Audio generation client API for TTS services.

Supports multiple TTS backends:
- OpenAI TTS (gpt-4o-mini-tts)
- Amazon Polly (Neural)
- Azure Cognitive Services TTS
- Google Cloud Text-to-Speech
"""

from .azure_tts import AzureTTSClient, AzureVoice
from .google_tts import GoogleTTSClient, GoogleTtsVoice
from .openai_tts import OpenAITTSClient, generate_audio
from .polly_tts import PollyTTSClient, PollyVoice
from .s3_uploader import S3AudioUploader, get_uploader, upload_audio_file
from .types import AudioFormat, AudioGenerationResult, Voice

__all__ = [
    "OpenAITTSClient",
    "generate_audio",
    "AudioGenerationResult",
    "Voice",
    "AudioFormat",
    "S3AudioUploader",
    "upload_audio_file",
    "get_uploader",
    "PollyTTSClient",
    "PollyVoice",
    "AzureTTSClient",
    "AzureVoice",
    "GoogleTTSClient",
    "GoogleTtsVoice",
]
