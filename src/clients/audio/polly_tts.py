#!/usr/bin/python3
"""Amazon Polly TTS client for audio generation.

Uses boto3 to interact with Amazon Polly's Neural and Generative engine
for high-quality text-to-speech. API key is loaded from keys/polly.key
with the format:
    Line 1: AWS Access Key ID
    Line 2: AWS Secret Access Key
    Line 3: AWS Region (optional, defaults to us-east-1)
"""

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from clients.keys import load_key

from .types import AudioFormat, AudioGenerationResult

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_ENGINE = "neural"
DEFAULT_REGION = "us-east-1"
DEFAULT_TIMEOUT = 60

# Audio format mapping: our AudioFormat -> Polly OutputFormat
POLLY_FORMAT_MAP: Dict[AudioFormat, str] = {
    AudioFormat.MP3: "mp3",
    AudioFormat.OPUS: "ogg_vorbis",
    AudioFormat.PCM: "pcm",
}


class PollyVoice(Enum):
    """Available Amazon Polly Neural voices for supported languages.

    Each value is (voice_id, language_code, gender, engine, description).
    """

    # Chinese (Mandarin) voices
    ZHIYU = ("Zhiyu", "zh", "f", "neural", "Chinese Mandarin female")

    # Spanish voices
    LUPE = ("Lupe", "es", "f", "neural", "Spanish (US) female")
    PEDRO = ("Pedro", "es", "m", "neural", "Spanish (US) male")
    MIA = ("Mia", "es", "f", "neural", "Spanish (MX) female")
    ANDRES = ("Andrés", "es", "m", "neural", "Spanish (MX) male")
    SERGIO = ("Sergio", "es", "m", "neural", "Spanish (ES) male")
    LUCIA = ("Lucia", "es", "f", "neural", "Spanish (ES) female")

    # French voices
    LEA = ("Léa", "fr", "f", "neural", "French (FR) female")
    REMI = ("Rémi", "fr", "m", "neural", "French (FR) male")

    # Korean voices
    SEOYEON = ("Seoyeon", "ko", "f", "neural", "Korean female")

    # German voices
    VICKI = ("Vicki", "de", "f", "neural", "German female")
    DANIEL = ("Daniel", "de", "m", "neural", "German male")

    # Portuguese voices
    CAMILA = ("Camila", "pt", "f", "neural", "Portuguese (BR) female")
    THIAGO = ("Thiago", "pt", "m", "neural", "Portuguese (BR) male")

    # Vietnamese voices
    # (Polly does not have Vietnamese neural voices as of 2025)

    @property
    def voice_id(self) -> str:
        """Get the Polly voice ID."""
        return self.value[0]

    @property
    def language_code(self) -> str:
        """Get the language code."""
        return self.value[1]

    @property
    def gender(self) -> str:
        """Get the gender ('m' or 'f')."""
        return self.value[2]

    @property
    def engine(self) -> str:
        """Get the Polly engine type."""
        return self.value[3]

    @property
    def description(self) -> str:
        """Get the voice description."""
        return self.value[4]

    @property
    def ui_name(self) -> str:
        """Get display name for UI."""
        return f"polly-{self.voice_id.lower()}"

    @classmethod
    def get_voices_for_language(cls, language_code: str) -> List["PollyVoice"]:
        """Get all available voices for a specific language."""
        return [v for v in cls if v.language_code == language_code]


# Polly language code mapping: our codes -> Polly LanguageCode
POLLY_LANGUAGE_CODES: Dict[str, str] = {
    "zh": "cmn-CN",
    "es": "es-ES",
    "fr": "fr-FR",
    "ko": "ko-KR",
    "de": "de-DE",
    "pt": "pt-BR",
    "en": "en-US",
}


def _load_polly_credentials() -> tuple[Optional[str], Optional[str], str]:
    """Load AWS credentials from keys/polly.key.

    Returns:
        Tuple of (access_key_id, secret_access_key, region)
    """
    import constants

    key_path = f"{constants.KEY_DIR}/polly.key"
    try:
        with open(key_path) as f:
            lines = [line.strip() for line in f.readlines()]
        if len(lines) >= 2:
            access_key = lines[0]
            secret_key = lines[1]
            region = lines[2] if len(lines) >= 3 and lines[2] else DEFAULT_REGION
            return access_key, secret_key, region
        logger.warning(f"Polly key file {key_path} has insufficient lines (need at least 2)")
        return None, None, DEFAULT_REGION
    except FileNotFoundError:
        logger.warning(f"Polly key file not found at {key_path}")
        return None, None, DEFAULT_REGION
    except Exception as e:
        logger.error(f"Error loading Polly credentials: {e}")
        return None, None, DEFAULT_REGION


class PollyTTSClient:
    """Client for generating audio using Amazon Polly."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False) -> None:
        """Initialize Amazon Polly TTS client.

        Args:
            timeout: Request timeout in seconds
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)

        self.access_key: Optional[str]
        self.secret_key: Optional[str]
        self.access_key, self.secret_key, self.region = _load_polly_credentials()
        self.polly_client: Any = None

        if self.access_key and self.secret_key:
            try:
                import boto3

                self.polly_client = boto3.client(
                    "polly",
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                )
                logger.info(f"Polly client initialized (region: {self.region})")
            except ImportError:
                logger.error(
                    "boto3 is required for Amazon Polly TTS. Install with: pip install boto3"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Polly client: {e}")

    def generate_audio(
        self,
        text: str,
        voice: PollyVoice = PollyVoice.LUPE,
        language_code: str = "es",
        audio_format: AudioFormat = AudioFormat.MP3,
        engine: str = DEFAULT_ENGINE,
    ) -> AudioGenerationResult:
        """Generate audio from text using Amazon Polly.

        Args:
            text: Text to convert to speech
            voice: PollyVoice enum for voice selection
            language_code: Language code for the text
            audio_format: Output audio format
            engine: Polly engine type ('neural' or 'generative')

        Returns:
            AudioGenerationResult with audio data and metadata
        """
        if not self.polly_client:
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=language_code,
                model=f"polly-{engine}",
                duration_ms=0,
                success=False,
                error="Amazon Polly client not initialized. Check keys/polly.key.",
            )

        start_time = time.time()

        # Map our format to Polly's format
        output_format = POLLY_FORMAT_MAP.get(audio_format, "mp3")

        # Get the Polly language code
        polly_lang_code = POLLY_LANGUAGE_CODES.get(language_code)

        try:
            synth_params: Dict[str, Any] = {
                "Text": text,
                "VoiceId": voice.voice_id,
                "OutputFormat": output_format,
                "Engine": engine,
            }
            if polly_lang_code:
                synth_params["LanguageCode"] = polly_lang_code

            logger.info(f"Making Polly API call: voice={voice.voice_id}, engine={engine}")

            response = self.polly_client.synthesize_speech(**synth_params)

            # Read audio stream
            audio_data = response["AudioStream"].read()
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Polly TTS Complete - {len(audio_data)} bytes, " f"Time: {duration_ms:.0f}ms"
            )

            return AudioGenerationResult(
                audio_data=audio_data,
                text=text,
                voice=None,
                language_code=language_code,
                model=f"polly-{engine}",
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except Exception as e:
            error_msg = f"Polly TTS error: {str(e)}"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=language_code,
                model=f"polly-{engine}",
                duration_ms=0,
                success=False,
                error=error_msg,
            )
