#!/usr/bin/python3
"""Google Cloud Text-to-Speech client for audio generation.

Uses the Google Cloud TTS REST API for text-to-speech.
API key is loaded from keys/google_tts.key with the format:
    Line 1: Google Cloud API key
"""

import base64
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

import requests

from clients.keys import load_key

from .types import AudioFormat, AudioGenerationResult

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_TIMEOUT = 60
API_BASE = "https://texttospeech.googleapis.com/v1"

# Audio format mapping: our AudioFormat -> Google TTS audioEncoding
GOOGLE_FORMAT_MAP: Dict[AudioFormat, str] = {
    AudioFormat.MP3: "MP3",
    AudioFormat.WAV: "LINEAR16",
    AudioFormat.OPUS: "OGG_OPUS",
}


class GoogleTtsVoice(Enum):
    """Available Google Cloud TTS voices for supported languages.

    Each value is (voice_name, language_code, gender, voice_type, description).
    voice_type is 'Wavenet', 'Neural2', or 'Standard'.
    """

    # Lithuanian voices
    LT_STANDARD_A = ("lt-LT-Standard-A", "lt", "m", "Standard", "Lithuanian male")

    # Chinese (Mandarin) voices
    ZH_WAVENET_A = ("cmn-CN-Wavenet-A", "zh", "f", "Wavenet", "Chinese female")
    ZH_WAVENET_B = ("cmn-CN-Wavenet-B", "zh", "m", "Wavenet", "Chinese male")
    ZH_WAVENET_C = ("cmn-CN-Wavenet-C", "zh", "m", "Wavenet", "Chinese male (alt)")
    ZH_WAVENET_D = ("cmn-CN-Wavenet-D", "zh", "f", "Wavenet", "Chinese female (alt)")

    # Spanish voices
    ES_WAVENET_B = ("es-ES-Wavenet-B", "es", "m", "Wavenet", "Spanish male")
    ES_WAVENET_C = ("es-ES-Wavenet-C", "es", "f", "Wavenet", "Spanish female")
    ES_WAVENET_D = ("es-ES-Wavenet-D", "es", "f", "Wavenet", "Spanish female (alt)")
    ES_NEURAL2_A = ("es-ES-Neural2-A", "es", "f", "Neural2", "Spanish female (Neural2)")
    ES_NEURAL2_B = ("es-ES-Neural2-B", "es", "m", "Neural2", "Spanish male (Neural2)")

    # French voices
    FR_WAVENET_A = ("fr-FR-Wavenet-A", "fr", "f", "Wavenet", "French female")
    FR_WAVENET_B = ("fr-FR-Wavenet-B", "fr", "m", "Wavenet", "French male")
    FR_WAVENET_C = ("fr-FR-Wavenet-C", "fr", "f", "Wavenet", "French female (alt)")
    FR_WAVENET_D = ("fr-FR-Wavenet-D", "fr", "m", "Wavenet", "French male (alt)")
    FR_NEURAL2_A = ("fr-FR-Neural2-A", "fr", "f", "Neural2", "French female (Neural2)")

    # Korean voices
    KO_WAVENET_A = ("ko-KR-Wavenet-A", "ko", "f", "Wavenet", "Korean female")
    KO_WAVENET_B = ("ko-KR-Wavenet-B", "ko", "f", "Wavenet", "Korean female (alt)")
    KO_WAVENET_C = ("ko-KR-Wavenet-C", "ko", "m", "Wavenet", "Korean male")
    KO_WAVENET_D = ("ko-KR-Wavenet-D", "ko", "m", "Wavenet", "Korean male (alt)")

    # German voices
    DE_WAVENET_A = ("de-DE-Wavenet-A", "de", "f", "Wavenet", "German female")
    DE_WAVENET_B = ("de-DE-Wavenet-B", "de", "m", "Wavenet", "German male")
    DE_NEURAL2_A = ("de-DE-Neural2-A", "de", "f", "Neural2", "German female (Neural2)")
    DE_NEURAL2_B = ("de-DE-Neural2-B", "de", "m", "Neural2", "German male (Neural2)")

    # Portuguese voices
    PT_WAVENET_A = ("pt-BR-Wavenet-A", "pt", "f", "Wavenet", "Portuguese (BR) female")
    PT_WAVENET_B = ("pt-BR-Wavenet-B", "pt", "m", "Wavenet", "Portuguese (BR) male")
    PT_NEURAL2_A = ("pt-BR-Neural2-A", "pt", "f", "Neural2", "Portuguese (BR) female (Neural2)")

    # Vietnamese voices
    VI_WAVENET_A = ("vi-VN-Wavenet-A", "vi", "f", "Wavenet", "Vietnamese female")
    VI_WAVENET_B = ("vi-VN-Wavenet-B", "vi", "m", "Wavenet", "Vietnamese male")
    VI_WAVENET_C = ("vi-VN-Wavenet-C", "vi", "f", "Wavenet", "Vietnamese female (alt)")
    VI_WAVENET_D = ("vi-VN-Wavenet-D", "vi", "m", "Wavenet", "Vietnamese male (alt)")

    @property
    def voice_name(self) -> str:
        """Get the Google Cloud TTS voice name."""
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
    def voice_type(self) -> str:
        """Get the voice type (Wavenet, Neural2, Standard)."""
        return self.value[3]

    @property
    def description(self) -> str:
        """Get the voice description."""
        return self.value[4]

    @property
    def ui_name(self) -> str:
        """Get display name for UI."""
        return f"google-{self.name.lower()}"

    @property
    def google_language_code(self) -> str:
        """Get the full Google language code from the voice name (e.g., 'cmn-CN')."""
        parts = self.voice_name.rsplit("-", 2)
        return f"{parts[0]}" if len(parts) >= 3 else self.voice_name.rsplit("-", 1)[0]

    @classmethod
    def get_voices_for_language(cls, language_code: str) -> List["GoogleTtsVoice"]:
        """Get all available voices for a specific language."""
        return [v for v in cls if v.language_code == language_code]


# Gender mapping for Google TTS API
GOOGLE_GENDER_MAP: Dict[str, str] = {
    "m": "MALE",
    "f": "FEMALE",
}


class GoogleTTSClient:
    """Client for generating audio using Google Cloud Text-to-Speech."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False) -> None:
        """Initialize Google Cloud TTS client.

        Args:
            timeout: Request timeout in seconds
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)

        self.api_key = load_key("google_tts", required=False)
        if self.api_key:
            logger.info("Google Cloud TTS client initialized")
        else:
            logger.warning("Google Cloud TTS API key not available")

    def generate_audio(
        self,
        text: str,
        voice: GoogleTtsVoice = GoogleTtsVoice.ES_WAVENET_C,
        language_code: str = "es",
        audio_format: AudioFormat = AudioFormat.MP3,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
    ) -> AudioGenerationResult:
        """Generate audio from text using Google Cloud TTS.

        Args:
            text: Text to convert to speech
            voice: GoogleTtsVoice enum for voice selection
            language_code: Language code for the text
            audio_format: Output audio format
            speaking_rate: Speed of speech (0.25 to 4.0, default 1.0)
            pitch: Pitch adjustment in semitones (-20.0 to 20.0, default 0.0)

        Returns:
            AudioGenerationResult with audio data and metadata
        """
        if not self.api_key:
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=language_code,
                model=f"google-{voice.voice_type.lower()}",
                duration_ms=0,
                success=False,
                error="Google Cloud TTS API key not available. Check keys/google_tts.key.",
            )

        start_time = time.time()

        # Get audio encoding
        audio_encoding = GOOGLE_FORMAT_MAP.get(audio_format, "MP3")

        # Get ssml gender
        ssml_gender = GOOGLE_GENDER_MAP.get(voice.gender, "FEMALE")

        # Build request payload
        payload: Dict[str, Any] = {
            "input": {"text": text},
            "voice": {
                "languageCode": voice.google_language_code,
                "name": voice.voice_name,
                "ssmlGender": ssml_gender,
            },
            "audioConfig": {
                "audioEncoding": audio_encoding,
                "speakingRate": speaking_rate,
                "pitch": pitch,
            },
        }

        url = f"{API_BASE}/text:synthesize?key={self.api_key}"

        try:
            logger.info(f"Making Google TTS API call: voice={voice.voice_name}")

            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                error_msg = f"Google TTS API error {response.status_code}: {response.text}"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=language_code,
                    model=f"google-{voice.voice_type.lower()}",
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            # Decode base64 audio content
            response_data = response.json()
            audio_content_b64 = response_data.get("audioContent", "")
            audio_data = base64.b64decode(audio_content_b64)

            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Google TTS Complete - {len(audio_data)} bytes, " f"Time: {duration_ms:.0f}ms"
            )

            return AudioGenerationResult(
                audio_data=audio_data,
                text=text,
                voice=None,
                language_code=language_code,
                model=f"google-{voice.voice_type.lower()}",
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except Exception as e:
            error_msg = f"Google TTS error: {str(e)}"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=language_code,
                model=f"google-{voice.voice_type.lower()}",
                duration_ms=0,
                success=False,
                error=error_msg,
            )
