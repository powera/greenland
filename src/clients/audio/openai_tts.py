#!/usr/bin/python3
"""OpenAI TTS client for audio generation."""

import os
import time
import logging
from pathlib import Path
from typing import Optional

import requests

import constants
from .types import Voice, AudioFormat, AudioGenerationResult

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_MODEL = "gpt-4o-mini-tts"
API_BASE = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60

# Language-specific TTS instructions
LANGUAGE_INSTRUCTIONS = {
    "lt": """Pronounce this Lithuanian word or phrase with clear, accurate pronunciation:
- Emphasize proper Lithuanian vowel length and stress patterns
- Maintain proper Lithuanian intonation with a natural rise and fall
- Articulate each syllable distinctly without rushing
- Use standard Lithuanian pronunciation, not dialectal variants
- Pronounce every phoneme fully - do not drop consonant clusters or reduce unstressed vowels
- For phrases, maintain proper spacing and natural flow between words""",
    "zh": """Pronounce this Chinese word or phrase with clear, accurate pronunciation:
- Use proper Mandarin tones and pronunciation
- Articulate each syllable clearly
- Maintain natural Chinese intonation""",
    "ko": """Pronounce this Korean word or phrase with clear, accurate pronunciation:
- Use proper Korean pronunciation and intonation
- Articulate each syllable clearly""",
    "fr": """Pronounce this French word or phrase with clear, accurate pronunciation:
- Use proper French pronunciation and intonation
- Maintain proper French vowel sounds""",
    "de": """Pronounce this German word or phrase with clear, accurate pronunciation:
- Use proper German pronunciation and intonation
- Maintain proper German vowel and consonant sounds""",
    "es": """Pronounce this Spanish word or phrase with clear, accurate pronunciation:
- Use proper Spanish pronunciation and intonation
- Maintain proper Spanish vowel sounds""",
    "pt": """Pronounce this Portuguese word or phrase with clear, accurate pronunciation:
- Use proper Portuguese pronunciation and intonation
- Maintain proper Portuguese vowel sounds""",
    "sw": """Pronounce this Swahili word or phrase with clear, accurate pronunciation:
- Use proper Swahili pronunciation and intonation
- Articulate each syllable clearly""",
    "vi": """Pronounce this Vietnamese word or phrase with clear, accurate pronunciation:
- Use proper Vietnamese tones and pronunciation
- Articulate each syllable clearly""",
}


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

        self.api_key = self._load_key()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _load_key(self) -> str:
        """Load OpenAI API key from file."""
        key_path = os.path.join(constants.KEY_DIR, "openai.key")
        with open(key_path) as f:
            return f.read().strip()

    def generate_audio(
        self,
        text: str,
        voice: Voice = Voice.ALLOY,
        language_code: str = "lt",
        model: str = DEFAULT_MODEL,
        audio_format: AudioFormat = AudioFormat.MP3,
        speed: float = 1.0,
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

        Returns:
            AudioGenerationResult with audio data and metadata
        """
        start_time = time.time()

        if self.debug:
            logger.debug(f"Generating audio for text: {text}")
            logger.debug(f"Voice: {voice.value}, Language: {language_code}")

        # Get language-specific instructions
        instructions = LANGUAGE_INSTRUCTIONS.get(language_code, "Speak clearly and naturally.")

        # Prepare request payload
        payload = {
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

            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )

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
                    error=error_msg
                )

            duration_ms = (time.time() - start_time) * 1000
            audio_data = response.content

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
                error=None
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
                error=error_msg
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

    Returns:
        AudioGenerationResult with audio data and metadata
    """
    return client.generate_audio(text, voice, language_code, model, audio_format, speed)
