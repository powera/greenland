#!/usr/bin/python3
"""Gemini 3.8 text-to-speech client.

Uses the Gemini Interactions API, which returns encoded audio in a model-output
content block.  The engine is exposed as plain "gemini"; the model is the
DEFAULT_GEMINI_TTS_MODEL setting, overridable per call via ``model``.
"""

import base64
import binascii
import logging
import re
import subprocess
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import requests

import clients.lib
from clients.keys import load_key

from .openai_tts import get_instructions
from .types import AudioFormat, AudioGenerationResult

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_TIMEOUT = 120
GEMINI_38_FLASH_TTS = "gemini-3.8-flash-tts"
GEMINI_38_FLASH_LITE_TTS = "gemini-3.8-flash-lite-tts"
GEMINI_TTS_MODELS = (GEMINI_38_FLASH_TTS, GEMINI_38_FLASH_LITE_TTS)
GEMINI_ENGINE = "gemini"
DEFAULT_GEMINI_TTS_MODEL = GEMINI_38_FLASH_TTS

# Gemini 3.8 Flash supports every tier 1-3 language.  Flash-Lite's published
# table omits Lithuanian, Swedish, Thai, and Swahili.  Spanish presentation and
# storage dialects use the same Spanish model capability with dialect prompts.
GEMINI_38_FLASH_TTS_LANGUAGES = frozenset(
    {
        "lt",
        "zh",
        "fr",
        "es",
        "de",
        "it",
        "nl",
        "pt",
        "sv",
        "vi",
        "ja",
        "ko",
        "ro",
        "pl",
        "th",
        "ta",
        "kn",
        "uk",
        "bn",
        "sw",
        "hi",
        "pa",
        "es-mx",
        "es-419",
        "zh-tw",
        "pt-br",
    }
)
GEMINI_38_FLASH_LITE_TTS_LANGUAGES = GEMINI_38_FLASH_TTS_LANGUAGES - {
    "lt",
    "sv",
    "th",
    "sw",
}

# The Interactions API documents only WAV and raw PCM output ("audio/mp3" is
# rejected with a 400 most of the time), so every request asks for WAV and any
# other format is transcoded locally with ffmpeg.  Values are ffmpeg output args.
GEMINI_RESPONSE_MIME_TYPE = "audio/wav"
GEMINI_FORMAT_MAP: Dict[AudioFormat, Optional[List[str]]] = {
    AudioFormat.WAV: None,
    AudioFormat.MP3: ["-codec:a", "libmp3lame", "-q:a", "2", "-f", "mp3"],
    AudioFormat.OPUS: ["-codec:a", "libopus", "-f", "ogg"],
}
FFMPEG_TIMEOUT = 60

# Tier 1 allows 10 requests per minute, and a 429 names the wait ("Please retry
# in 53s").  Batch runs rely on this rather than pacing themselves.
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RATE_LIMIT_WAIT = 60
RETRY_AFTER_PATTERN = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)


class GeminiTtsVoice(Enum):
    """The Gemini prebuilt voices Greenland uses (of Google's 30).

    Each value contains the API voice name, perceived gender, and Google's
    short style description.  Chosen for clarity: two female, two male.
    """

    ERINOME = ("Erinome", "f", "Clear")
    IAPETUS = ("Iapetus", "m", "Clear")
    KORE = ("Kore", "f", "Firm")
    CHARON = ("Charon", "m", "Informative")

    @property
    def voice_name(self) -> str:
        return str(self.value[0])

    @property
    def gender(self) -> str:
        return str(self.value[1])

    @property
    def description(self) -> str:
        return str(self.value[2])

    @property
    def storage_name(self) -> str:
        """Return the path/review name."""
        return self.voice_name.lower()

    @classmethod
    def from_identifier(cls, identifier: str) -> Optional["GeminiTtsVoice"]:
        """Resolve a voice from its storage name or API voice name."""
        normalized_identifier = identifier.lower()
        for gemini_voice in cls:
            if normalized_identifier == gemini_voice.storage_name:
                return gemini_voice
        return None

    @classmethod
    def get_voices_for_language(
        cls, language_code: str, model: str = DEFAULT_GEMINI_TTS_MODEL
    ) -> List["GeminiTtsVoice"]:
        """Return prebuilt voices when the model supports the language."""
        supported_languages = get_supported_languages(model)
        return list(cls) if language_code.lower() in supported_languages else []


DEFAULT_GEMINI_VOICES = (GeminiTtsVoice.ERINOME, GeminiTtsVoice.IAPETUS)


def get_supported_languages(model: str) -> frozenset[str]:
    """Return the configured tier 1-3 languages supported by a Gemini model."""
    if model == GEMINI_38_FLASH_TTS:
        return GEMINI_38_FLASH_TTS_LANGUAGES
    if model == GEMINI_38_FLASH_LITE_TTS:
        return GEMINI_38_FLASH_LITE_TTS_LANGUAGES
    raise ValueError(f"Unsupported Gemini TTS model: {model}")


def _extract_audio(response_data: Dict[str, Any]) -> Tuple[bytes, Optional[str]]:
    """Extract the last inline audio block from an Interactions response."""
    steps = response_data.get("steps", [])
    for step in reversed(steps):
        content_blocks = step.get("content", []) if isinstance(step, dict) else []
        for content_block in reversed(content_blocks):
            if isinstance(content_block, dict) and content_block.get("type") == "audio":
                encoded_audio = content_block.get("data")
                if isinstance(encoded_audio, str) and encoded_audio:
                    return base64.b64decode(encoded_audio), content_block.get("mime_type")
    raise ValueError("Gemini TTS response did not contain inline audio data")


def _rate_limit_wait_seconds(response_text: str) -> float:
    """Return the wait a 429 body asks for, or a full minute if it names none."""
    match = RETRY_AFTER_PATTERN.search(response_text)
    return float(match.group(1)) + 1 if match else DEFAULT_RATE_LIMIT_WAIT


def _transcode_wav(wav_data: bytes, ffmpeg_args: List[str]) -> bytes:
    """Convert WAV bytes to another format by piping them through ffmpeg."""
    try:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                *ffmpeg_args,
                "pipe:1",
            ],
            input=wav_data,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"ffmpeg transcode failed: {exc}") from exc
    if completed.returncode != 0 or not completed.stdout:
        stderr_text = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"ffmpeg transcode failed: {stderr_text}")
    return completed.stdout


class GeminiTTSClient:
    """Generate single-speaker audio with Gemini 3.8 TTS."""

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        debug: bool = False,
        api_key: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.debug = debug
        self.api_key = api_key if api_key else load_key("gemini", required=False)
        if debug:
            logger.setLevel(logging.DEBUG)

    def generate_audio(
        self,
        text: str,
        voice: GeminiTtsVoice = GeminiTtsVoice.ERINOME,
        language_code: str = "es",
        model: str = DEFAULT_GEMINI_TTS_MODEL,
        audio_format: AudioFormat = AudioFormat.MP3,
        is_sentence: bool = False,
    ) -> AudioGenerationResult:
        """Generate audio using the Gemini Interactions API."""
        if not self.api_key:
            return self._error_result(text, language_code, model, "Gemini API key not available")
        if model not in GEMINI_TTS_MODELS:
            return self._error_result(text, language_code, model, f"Unsupported model: {model}")
        if language_code.lower() not in get_supported_languages(model):
            return self._error_result(
                text,
                language_code,
                model,
                f"{model} does not support language '{language_code}'",
            )
        if audio_format not in GEMINI_FORMAT_MAP:
            return self._error_result(
                text, language_code, model, f"Unsupported audio format: {audio_format.value}"
            )

        clients.lib.assert_llm_calls_enabled("gemini-tts")
        style = get_instructions(language_code, is_sentence=is_sentence)
        payload: Dict[str, Any] = {
            "model": model,
            "input": [
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                            "annotations": [{"type": "speech_metadata", "style": style}],
                        }
                    ],
                }
            ],
            "response_format": {"type": "audio", "mime_type": GEMINI_RESPONSE_MIME_TYPE},
            "generation_config": {"speech_config": [{"voice": voice.voice_name}]},
            "store": False,
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        start_time = time.time()
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=self.timeout)
            for retry_number in range(1, MAX_RATE_LIMIT_RETRIES + 1):
                if response.status_code != 429:
                    break
                wait_seconds = _rate_limit_wait_seconds(response.text)
                logger.warning(
                    "Gemini TTS rate limited; waiting %.0fs (retry %d/%d)",
                    wait_seconds,
                    retry_number,
                    MAX_RATE_LIMIT_RETRIES,
                )
                time.sleep(wait_seconds)
                response = requests.post(
                    API_URL, headers=headers, json=payload, timeout=self.timeout
                )
            if response.status_code != 200:
                return self._error_result(
                    text,
                    language_code,
                    model,
                    f"Gemini TTS API error {response.status_code}: {response.text}",
                )
            audio_data, response_mime_type = _extract_audio(response.json())
            if self.debug:
                logger.debug(
                    "Gemini TTS returned %d bytes as %s",
                    len(audio_data),
                    response_mime_type,
                )
            ffmpeg_args = GEMINI_FORMAT_MAP[audio_format]
            if ffmpeg_args is not None:
                audio_data = _transcode_wav(audio_data, ffmpeg_args)
            return AudioGenerationResult(
                audio_data=audio_data,
                text=text,
                voice=None,
                language_code=language_code,
                model=model,
                duration_ms=(time.time() - start_time) * 1000,
            )
        except (requests.RequestException, ValueError, KeyError, binascii.Error) as exc:
            return self._error_result(text, language_code, model, f"Gemini TTS error: {exc}")

    @staticmethod
    def _error_result(
        text: str, language_code: str, model: str, error: str
    ) -> AudioGenerationResult:
        logger.error(error)
        return AudioGenerationResult(
            audio_data=b"",
            text=text,
            voice=None,
            language_code=language_code,
            model=model,
            duration_ms=0,
            success=False,
            error=error,
        )
