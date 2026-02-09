#!/usr/bin/python3
"""Azure Cognitive Services TTS client for audio generation.

Uses the Azure Speech Services REST API for text-to-speech.
API key is loaded from keys/azure_tts.key with the format:
    Line 1: Subscription Key
    Line 2: Region (e.g., eastus, westus2, westeurope)
"""

import logging
import time
from enum import Enum
from typing import Dict, List, Optional

import requests

from .types import AudioFormat, AudioGenerationResult

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_TIMEOUT = 60
DEFAULT_REGION = "eastus"

# Audio format mapping: our AudioFormat -> Azure output format header value
AZURE_FORMAT_MAP: Dict[AudioFormat, str] = {
    AudioFormat.MP3: "audio-24khz-96kbitrate-mono-mp3",
    AudioFormat.WAV: "riff-24khz-16bit-mono-pcm",
    AudioFormat.OPUS: "ogg-24khz-16bit-mono-opus",
}


class AzureVoice(Enum):
    """Available Azure Neural TTS voices for supported languages.

    Each value is (voice_name, language_code, gender, description).
    The voice_name is the full Azure voice identifier.
    """

    # Lithuanian voices
    ONA = ("lt-LT-OnaNeural", "lt", "f", "Lithuanian female")
    LEONAS = ("lt-LT-LeonasNeural", "lt", "m", "Lithuanian male")

    # Chinese (Mandarin) voices
    XIAOXIAO = ("zh-CN-XiaoxiaoNeural", "zh", "f", "Chinese female (warm)")
    YUNXI = ("zh-CN-YunxiNeural", "zh", "m", "Chinese male (cheerful)")
    XIAOYI = ("zh-CN-XiaoyiNeural", "zh", "f", "Chinese female (lively)")
    YUNJIAN = ("zh-CN-YunjianNeural", "zh", "m", "Chinese male (sports)")

    # Spanish voices
    ELVIRA = ("es-ES-ElviraNeural", "es", "f", "Spanish (ES) female")
    ALVARO = ("es-ES-AlvaroNeural", "es", "m", "Spanish (ES) male")
    DALIA = ("es-MX-DaliaNeural", "es", "f", "Spanish (MX) female")
    JORGE = ("es-MX-JorgeNeural", "es", "m", "Spanish (MX) male")

    # French voices
    DENISE = ("fr-FR-DeniseNeural", "fr", "f", "French female")
    HENRI = ("fr-FR-HenriNeural", "fr", "m", "French male")

    # Korean voices
    SUNHI = ("ko-KR-SunHiNeural", "ko", "f", "Korean female")
    INJOONG = ("ko-KR-InJoonNeural", "ko", "m", "Korean male")

    # German voices
    KATJA = ("de-DE-KatjaNeural", "de", "f", "German female")
    CONRAD = ("de-DE-ConradNeural", "de", "m", "German male")

    # Portuguese voices
    FRANCISCA = ("pt-BR-FranciscaNeural", "pt", "f", "Portuguese (BR) female")
    ANTONIO = ("pt-BR-AntonioNeural", "pt", "m", "Portuguese (BR) male")

    # Swahili voices
    ZURI = ("sw-KE-ZuriNeural", "sw", "f", "Swahili female")
    RAFIKI = ("sw-KE-RafikiNeural", "sw", "m", "Swahili male")

    # Vietnamese voices
    HOAIMY = ("vi-VN-HoaiMyNeural", "vi", "f", "Vietnamese female")
    NAMMINH = ("vi-VN-NamMinhNeural", "vi", "m", "Vietnamese male")

    @property
    def voice_name(self) -> str:
        """Get the Azure voice identifier."""
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
    def description(self) -> str:
        """Get the voice description."""
        return self.value[3]

    @property
    def ui_name(self) -> str:
        """Get display name for UI."""
        return f"azure-{self.name.lower()}"

    @classmethod
    def get_voices_for_language(cls, language_code: str) -> List["AzureVoice"]:
        """Get all available voices for a specific language."""
        return [v for v in cls if v.language_code == language_code]


def _load_azure_credentials() -> tuple[Optional[str], str]:
    """Load Azure credentials from keys/azure_tts.key.

    Returns:
        Tuple of (subscription_key, region)
    """
    import constants

    key_path = f"{constants.KEY_DIR}/azure_tts.key"
    try:
        with open(key_path) as f:
            lines = [line.strip() for line in f.readlines()]
        if len(lines) >= 1 and lines[0]:
            subscription_key = lines[0]
            region = lines[1] if len(lines) >= 2 and lines[1] else DEFAULT_REGION
            return subscription_key, region
        logger.warning(f"Azure TTS key file {key_path} is empty")
        return None, DEFAULT_REGION
    except FileNotFoundError:
        logger.warning(f"Azure TTS key file not found at {key_path}")
        return None, DEFAULT_REGION
    except Exception as e:
        logger.error(f"Error loading Azure TTS credentials: {e}")
        return None, DEFAULT_REGION


class AzureTTSClient:
    """Client for generating audio using Azure Cognitive Services TTS."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False) -> None:
        """Initialize Azure TTS client.

        Args:
            timeout: Request timeout in seconds
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)

        self.subscription_key, self.region = _load_azure_credentials()
        self.endpoint = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"

        if self.subscription_key:
            logger.info(f"Azure TTS client initialized (region: {self.region})")
        else:
            logger.warning("Azure TTS subscription key not available")

    def generate_audio(
        self,
        text: str,
        voice: AzureVoice = AzureVoice.ELVIRA,
        language_code: str = "es",
        audio_format: AudioFormat = AudioFormat.MP3,
        rate: str = "0%",
    ) -> AudioGenerationResult:
        """Generate audio from text using Azure Cognitive TTS.

        Args:
            text: Text to convert to speech
            voice: AzureVoice enum for voice selection
            language_code: Language code for the text
            audio_format: Output audio format
            rate: Speech rate adjustment (e.g., '-10%', '+20%', '0%')

        Returns:
            AudioGenerationResult with audio data and metadata
        """
        if not self.subscription_key:
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=language_code,
                model="azure-neural",
                duration_ms=0,
                success=False,
                error="Azure TTS subscription key not available. Check keys/azure_tts.key.",
            )

        start_time = time.time()

        # Get output format
        output_format = AZURE_FORMAT_MAP.get(audio_format, "audio-24khz-96kbitrate-mono-mp3")

        # Build SSML
        xml_lang = voice.voice_name.rsplit("-", 1)[0]  # e.g., "lt-LT" from "lt-LT-OnaNeural"
        # Ensure the xml:lang matches the voice locale
        ssml = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{xml_lang}">'
            f'<voice name="{voice.voice_name}">'
        )
        if rate != "0%":
            ssml += f'<prosody rate="{rate}">{_escape_xml(text)}</prosody>'
        else:
            ssml += _escape_xml(text)
        ssml += "</voice></speak>"

        headers = {
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": output_format,
            "User-Agent": "greenland-tts",
        }

        try:
            logger.info(f"Making Azure TTS API call: voice={voice.voice_name}")

            response = requests.post(
                self.endpoint,
                headers=headers,
                data=ssml.encode("utf-8"),
                timeout=self.timeout,
            )

            if response.status_code != 200:
                error_msg = f"Azure TTS API error {response.status_code}: {response.text}"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=language_code,
                    model="azure-neural",
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            audio_data = response.content
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Azure TTS Complete - {len(audio_data)} bytes, " f"Time: {duration_ms:.0f}ms"
            )

            return AudioGenerationResult(
                audio_data=audio_data,
                text=text,
                voice=None,
                language_code=language_code,
                model="azure-neural",
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except Exception as e:
            error_msg = f"Azure TTS error: {str(e)}"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=language_code,
                model="azure-neural",
                duration_ms=0,
                success=False,
                error=error_msg,
            )


def _escape_xml(text: str) -> str:
    """Escape XML special characters in text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
