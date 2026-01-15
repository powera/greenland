#!/usr/bin/python3
"""OpenAI TTS client for audio generation."""

import logging
import time
from pathlib import Path
from typing import Any, Optional

import requests

import constants
from clients.keys import load_key

from .types import AudioFormat, AudioGenerationResult, Voice

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_MODEL = "gpt-4o-mini-tts"
API_BASE = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60

# Pricing estimates (as of Jan 2025)
# gpt-4o-mini-tts: $0.60/1M input tokens, $12/1M output audio tokens
# Empirically ~300 bytes per audio token, ~4 chars per input token
BYTES_PER_AUDIO_TOKEN = 300
CHARS_PER_INPUT_TOKEN = 4
PRICE_PER_1M_INPUT_TOKENS = 0.60
PRICE_PER_1M_OUTPUT_TOKENS = 12.00

# Path to prompts directory (ROOT/prompts/audio/)
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts" / "audio"

# Cache for loaded prompts
_prompt_cache: dict[tuple[str, str], str] = {}


def _load_prompt(prompt_type: str, language_code: str) -> str:
    """
    Load a prompt from file.

    Args:
        prompt_type: Either "word" or "sentence"
        language_code: Language code (e.g., "lt", "zh")

    Returns:
        The prompt text, or a default fallback if file not found
    """
    cache_key = (prompt_type, language_code)
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    prompt_file = PROMPTS_DIR / prompt_type / f"{language_code}.txt"
    if prompt_file.exists():
        prompt_text = prompt_file.read_text().strip()
        _prompt_cache[cache_key] = prompt_text
        return prompt_text

    # Fallback to default
    default_prompt = "Speak clearly and naturally."
    _prompt_cache[cache_key] = default_prompt
    return default_prompt


def get_instructions(language_code: str, is_sentence: bool = False) -> str:
    """
    Get TTS instructions for a language.

    Args:
        language_code: Language code (e.g., "lt", "zh")
        is_sentence: If True, use sentence-level prompt; otherwise use word-level

    Returns:
        The instruction text for TTS
    """
    prompt_type = "sentence" if is_sentence else "word"
    return _load_prompt(prompt_type, language_code)


class OpenAITTSClient:
    """Client for generating audio using OpenAI TTS API."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False):
        """
        Initialize OpenAI TTS client.

        Args:
            timeout: Request timeout in seconds
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized OpenAITTSClient in debug mode")

        self.api_key = load_key("openai", required=False)
        if self.api_key:
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.headers = {}

    def generate_audio(
        self,
        text: str,
        voice: Voice = Voice.ALLOY,
        language_code: str = "lt",
        model: str = DEFAULT_MODEL,
        audio_format: AudioFormat = AudioFormat.MP3,
        speed: float = 1.0,
        is_sentence: bool = False,
    ) -> AudioGenerationResult:
        """
        Generate audio from text using OpenAI TTS.

        Args:
            text: Text to convert to speech
            voice: Voice to use for generation
            language_code: Language code for pronunciation instructions
            model: TTS model to use
            audio_format: Output audio format
            speed: Speed of speech (0.25 to 4.0)
            is_sentence: If True, use sentence-level prompt for natural pacing

        Returns:
            AudioGenerationResult with audio data and metadata

        Raises:
            RuntimeError: If API key is not available
        """
        # Check if API key is available
        if not self.api_key:
            raise RuntimeError("OpenAI API key not available. Please ensure the key file exists.")

        start_time = time.time()

        if self.debug:
            logger.debug(f"Generating audio for text: {text}")
            logger.debug(f"Voice: {voice.value}, Language: {language_code}")

        # Get language-specific instructions
        instructions = get_instructions(language_code, is_sentence=is_sentence)

        # Prepare request payload
        payload: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice.value,
            "response_format": audio_format.value,
            "instructions": instructions,
        }

        # Add speed if not default
        if speed != 1.0:
            payload["speed"] = speed

        try:
            # Make API request
            url = f"{API_BASE}/audio/speech"

            # Log API call details
            logger.info(f"Making OpenAI TTS API call:")
            logger.info(f"  URL: {url}")
            logger.info(f"  Payload: {payload}")
            logger.info(f"  Timeout: {self.timeout}s")

            response = requests.post(url, headers=self.headers, json=payload, timeout=self.timeout)

            logger.info(f"API response status: {response.status_code}")

            if response.status_code != 200:
                error_msg = f"OpenAI TTS API error {response.status_code}: {response.text}"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=voice,
                    language_code=language_code,
                    model=model,
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            duration_ms = (time.time() - start_time) * 1000
            audio_data = response.content

            # Log input/output sizes and estimated cost
            input_chars = len(text) + len(instructions)
            input_tokens_est = input_chars / CHARS_PER_INPUT_TOKEN
            output_tokens_est = len(audio_data) / BYTES_PER_AUDIO_TOKEN
            cost_est = (
                input_tokens_est * PRICE_PER_1M_INPUT_TOKENS
                + output_tokens_est * PRICE_PER_1M_OUTPUT_TOKENS
            ) / 1_000_000
            logger.info(
                f"TTS Complete - In: ~{input_tokens_est:.0f} tokens, Out: ~{output_tokens_est:.0f} tokens, Cost: ~${cost_est:.6f}, Time: {duration_ms:.0f}ms"
            )

            if self.debug:
                logger.debug(f"Generated {len(audio_data)} bytes in {duration_ms:.0f}ms")

            return AudioGenerationResult(
                audio_data=audio_data,
                text=text,
                voice=voice,
                language_code=language_code,
                model=model,
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except Exception as e:
            error_msg = f"Error generating audio: {str(e)}"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=voice,
                language_code=language_code,
                model=model,
                duration_ms=0,
                success=False,
                error=error_msg,
            )


# Create default client instance
client = OpenAITTSClient(debug=False)


def generate_audio(
    text: str,
    voice: Voice = Voice.ALLOY,
    language_code: str = "lt",
    model: str = DEFAULT_MODEL,
    audio_format: AudioFormat = AudioFormat.MP3,
    speed: float = 1.0,
    is_sentence: bool = False,
) -> AudioGenerationResult:
    """
    Generate audio from text using OpenAI TTS.

    Convenience function that uses the default client instance.

    Args:
        text: Text to convert to speech
        voice: Voice to use for generation
        language_code: Language code for pronunciation instructions
        model: TTS model to use
        audio_format: Output audio format
        speed: Speed of speech (0.25 to 4.0)
        is_sentence: If True, use sentence-level prompt for natural pacing

    Returns:
        AudioGenerationResult with audio data and metadata
    """
    return client.generate_audio(
        text, voice, language_code, model, audio_format, speed, is_sentence
    )
