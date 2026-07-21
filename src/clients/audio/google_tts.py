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
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
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
    voice_type is 'Wavenet', 'Neural2', 'Studio', or 'Standard'.
    """

    # Arabic voices
    AR_WAVENET_A = ("ar-XA-Wavenet-A", "ar", "f", "Wavenet", "Arabic female")
    AR_WAVENET_B = ("ar-XA-Wavenet-B", "ar", "m", "Wavenet", "Arabic male")
    AR_WAVENET_C = ("ar-XA-Wavenet-C", "ar", "m", "Wavenet", "Arabic male (alt)")

    # Bengali voices
    BN_WAVENET_A = ("bn-IN-Wavenet-A", "bn", "f", "Wavenet", "Bengali female")
    BN_WAVENET_B = ("bn-IN-Wavenet-B", "bn", "m", "Wavenet", "Bengali male")

    # Catalan voices
    CA_WAVENET_A = ("ca-ES-Wavenet-A", "ca", "f", "Wavenet", "Catalan female")

    # Czech voices
    CS_WAVENET_A = ("cs-CZ-Wavenet-A", "cs", "f", "Wavenet", "Czech female")

    # Danish voices
    DA_WAVENET_A = ("da-DK-Wavenet-A", "da", "f", "Wavenet", "Danish female")
    DA_WAVENET_C = ("da-DK-Wavenet-C", "da", "m", "Wavenet", "Danish male")
    DA_WAVENET_D = ("da-DK-Wavenet-D", "da", "f", "Wavenet", "Danish female (alt)")
    DA_WAVENET_E = ("da-DK-Wavenet-E", "da", "f", "Wavenet", "Danish female (alt2)")

    # Dutch voices
    NL_WAVENET_A = ("nl-NL-Wavenet-A", "nl", "f", "Wavenet", "Dutch female")
    NL_WAVENET_B = ("nl-NL-Wavenet-B", "nl", "m", "Wavenet", "Dutch male")
    NL_WAVENET_C = ("nl-NL-Wavenet-C", "nl", "m", "Wavenet", "Dutch male (alt)")
    NL_WAVENET_D = ("nl-NL-Wavenet-D", "nl", "f", "Wavenet", "Dutch female (alt)")
    NL_WAVENET_E = ("nl-NL-Wavenet-E", "nl", "f", "Wavenet", "Dutch female (alt2)")

    # English voices
    EN_US_NEURAL2_A = ("en-US-Neural2-A", "en", "m", "Neural2", "English (US) male (Neural2)")
    EN_US_NEURAL2_C = ("en-US-Neural2-C", "en", "f", "Neural2", "English (US) female (Neural2)")
    EN_US_NEURAL2_D = ("en-US-Neural2-D", "en", "m", "Neural2", "English (US) male (Neural2, alt)")
    EN_US_NEURAL2_E = (
        "en-US-Neural2-E",
        "en",
        "f",
        "Neural2",
        "English (US) female (Neural2, alt)",
    )
    EN_US_NEURAL2_F = (
        "en-US-Neural2-F",
        "en",
        "f",
        "Neural2",
        "English (US) female (Neural2, alt2)",
    )
    EN_US_NEURAL2_G = (
        "en-US-Neural2-G",
        "en",
        "f",
        "Neural2",
        "English (US) female (Neural2, alt3)",
    )
    EN_US_NEURAL2_H = (
        "en-US-Neural2-H",
        "en",
        "f",
        "Neural2",
        "English (US) female (Neural2, alt4)",
    )
    EN_US_NEURAL2_I = ("en-US-Neural2-I", "en", "m", "Neural2", "English (US) male (Neural2, alt2)")
    EN_US_NEURAL2_J = ("en-US-Neural2-J", "en", "m", "Neural2", "English (US) male (Neural2, alt3)")
    EN_GB_NEURAL2_A = ("en-GB-Neural2-A", "en", "f", "Neural2", "English (GB) female (Neural2)")
    EN_GB_NEURAL2_B = ("en-GB-Neural2-B", "en", "m", "Neural2", "English (GB) male (Neural2)")
    EN_GB_NEURAL2_C = (
        "en-GB-Neural2-C",
        "en",
        "f",
        "Neural2",
        "English (GB) female (Neural2, alt)",
    )
    EN_GB_NEURAL2_D = ("en-GB-Neural2-D", "en", "m", "Neural2", "English (GB) male (Neural2, alt)")
    EN_GB_NEURAL2_F = (
        "en-GB-Neural2-F",
        "en",
        "f",
        "Neural2",
        "English (GB) female (Neural2, alt2)",
    )
    EN_AU_NEURAL2_A = ("en-AU-Neural2-A", "en", "f", "Neural2", "English (AU) female (Neural2)")
    EN_AU_NEURAL2_B = ("en-AU-Neural2-B", "en", "m", "Neural2", "English (AU) male (Neural2)")
    EN_AU_NEURAL2_C = (
        "en-AU-Neural2-C",
        "en",
        "f",
        "Neural2",
        "English (AU) female (Neural2, alt)",
    )
    EN_AU_NEURAL2_D = ("en-AU-Neural2-D", "en", "m", "Neural2", "English (AU) male (Neural2, alt)")
    EN_IN_WAVENET_A = ("en-IN-Wavenet-A", "en", "f", "Wavenet", "English (IN) female")
    EN_IN_WAVENET_B = ("en-IN-Wavenet-B", "en", "m", "Wavenet", "English (IN) male")
    EN_IN_WAVENET_C = ("en-IN-Wavenet-C", "en", "m", "Wavenet", "English (IN) male (alt)")
    EN_IN_WAVENET_D = ("en-IN-Wavenet-D", "en", "f", "Wavenet", "English (IN) female (alt)")

    # Filipino voices
    FIL_WAVENET_A = ("fil-PH-Wavenet-A", "tl", "f", "Wavenet", "Filipino female")
    FIL_WAVENET_B = ("fil-PH-Wavenet-B", "tl", "f", "Wavenet", "Filipino female (alt)")
    FIL_WAVENET_C = ("fil-PH-Wavenet-C", "tl", "m", "Wavenet", "Filipino male")
    FIL_WAVENET_D = ("fil-PH-Wavenet-D", "tl", "m", "Wavenet", "Filipino male (alt)")

    # Finnish voices
    FI_WAVENET_A = ("fi-FI-Wavenet-A", "fi", "f", "Wavenet", "Finnish female")

    # Greek voices
    EL_WAVENET_A = ("el-GR-Wavenet-A", "el", "f", "Wavenet", "Greek female")

    # Hindi voices
    HI_WAVENET_A = ("hi-IN-Wavenet-A", "hi", "f", "Wavenet", "Hindi female")
    HI_WAVENET_B = ("hi-IN-Wavenet-B", "hi", "m", "Wavenet", "Hindi male")
    HI_WAVENET_C = ("hi-IN-Wavenet-C", "hi", "m", "Wavenet", "Hindi male (alt)")
    HI_WAVENET_D = ("hi-IN-Wavenet-D", "hi", "f", "Wavenet", "Hindi female (alt)")

    # Hungarian voices
    HU_WAVENET_A = ("hu-HU-Wavenet-A", "hu", "f", "Wavenet", "Hungarian female")

    # Indonesian voices
    ID_WAVENET_A = ("id-ID-Wavenet-A", "id", "f", "Wavenet", "Indonesian female")
    ID_WAVENET_B = ("id-ID-Wavenet-B", "id", "m", "Wavenet", "Indonesian male")
    ID_WAVENET_C = ("id-ID-Wavenet-C", "id", "m", "Wavenet", "Indonesian male (alt)")
    ID_WAVENET_D = ("id-ID-Wavenet-D", "id", "f", "Wavenet", "Indonesian female (alt)")

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
    ES_NEURAL2_C = ("es-ES-Neural2-C", "es", "f", "Neural2", "Spanish female (Neural2, alt)")
    ES_NEURAL2_D = ("es-ES-Neural2-D", "es", "f", "Neural2", "Spanish female (Neural2, alt2)")
    ES_NEURAL2_E = ("es-ES-Neural2-E", "es", "f", "Neural2", "Spanish female (Neural2, alt3)")
    ES_NEURAL2_F = ("es-ES-Neural2-F", "es", "m", "Neural2", "Spanish male (Neural2, alt)")

    # French voices
    FR_WAVENET_A = ("fr-FR-Wavenet-A", "fr", "f", "Wavenet", "French female")
    FR_WAVENET_B = ("fr-FR-Wavenet-B", "fr", "m", "Wavenet", "French male")
    FR_WAVENET_C = ("fr-FR-Wavenet-C", "fr", "f", "Wavenet", "French female (alt)")
    FR_WAVENET_D = ("fr-FR-Wavenet-D", "fr", "m", "Wavenet", "French male (alt)")
    FR_WAVENET_E = ("fr-FR-Wavenet-E", "fr", "f", "Wavenet", "French female (alt2)")
    FR_NEURAL2_A = ("fr-FR-Neural2-A", "fr", "f", "Neural2", "French female (Neural2)")
    FR_NEURAL2_B = ("fr-FR-Neural2-B", "fr", "m", "Neural2", "French male (Neural2)")
    FR_NEURAL2_C = ("fr-FR-Neural2-C", "fr", "f", "Neural2", "French female (Neural2, alt)")
    FR_NEURAL2_D = ("fr-FR-Neural2-D", "fr", "m", "Neural2", "French male (Neural2, alt)")
    FR_NEURAL2_E = ("fr-FR-Neural2-E", "fr", "f", "Neural2", "French female (Neural2, alt2)")

    # Italian voices
    IT_WAVENET_A = ("it-IT-Wavenet-A", "it", "f", "Wavenet", "Italian female")
    IT_WAVENET_B = ("it-IT-Wavenet-B", "it", "f", "Wavenet", "Italian female (alt)")
    IT_WAVENET_C = ("it-IT-Wavenet-C", "it", "m", "Wavenet", "Italian male")
    IT_WAVENET_D = ("it-IT-Wavenet-D", "it", "m", "Wavenet", "Italian male (alt)")
    IT_NEURAL2_A = ("it-IT-Neural2-A", "it", "f", "Neural2", "Italian female (Neural2)")
    IT_NEURAL2_C = ("it-IT-Neural2-C", "it", "m", "Neural2", "Italian male (Neural2)")

    # Japanese voices
    JA_WAVENET_A = ("ja-JP-Wavenet-A", "ja", "f", "Wavenet", "Japanese female")
    JA_WAVENET_B = ("ja-JP-Wavenet-B", "ja", "f", "Wavenet", "Japanese female (alt)")
    JA_WAVENET_C = ("ja-JP-Wavenet-C", "ja", "m", "Wavenet", "Japanese male")
    JA_WAVENET_D = ("ja-JP-Wavenet-D", "ja", "m", "Wavenet", "Japanese male (alt)")
    JA_NEURAL2_B = ("ja-JP-Neural2-B", "ja", "f", "Neural2", "Japanese female (Neural2)")
    JA_NEURAL2_C = ("ja-JP-Neural2-C", "ja", "m", "Neural2", "Japanese male (Neural2)")
    JA_NEURAL2_D = ("ja-JP-Neural2-D", "ja", "m", "Neural2", "Japanese male (Neural2, alt)")

    # Korean voices
    KO_WAVENET_A = ("ko-KR-Wavenet-A", "ko", "f", "Wavenet", "Korean female")
    KO_WAVENET_B = ("ko-KR-Wavenet-B", "ko", "f", "Wavenet", "Korean female (alt)")
    KO_WAVENET_C = ("ko-KR-Wavenet-C", "ko", "m", "Wavenet", "Korean male")
    KO_WAVENET_D = ("ko-KR-Wavenet-D", "ko", "m", "Wavenet", "Korean male (alt)")
    KO_NEURAL2_A = ("ko-KR-Neural2-A", "ko", "f", "Neural2", "Korean female (Neural2)")
    KO_NEURAL2_B = ("ko-KR-Neural2-B", "ko", "f", "Neural2", "Korean female (Neural2, alt)")
    KO_NEURAL2_C = ("ko-KR-Neural2-C", "ko", "m", "Neural2", "Korean male (Neural2)")

    # German voices
    DE_WAVENET_A = ("de-DE-Wavenet-A", "de", "f", "Wavenet", "German female")
    DE_WAVENET_B = ("de-DE-Wavenet-B", "de", "m", "Wavenet", "German male")
    DE_WAVENET_C = ("de-DE-Wavenet-C", "de", "f", "Wavenet", "German female (alt)")
    DE_WAVENET_D = ("de-DE-Wavenet-D", "de", "m", "Wavenet", "German male (alt)")
    DE_WAVENET_E = ("de-DE-Wavenet-E", "de", "m", "Wavenet", "German male (alt2)")
    DE_WAVENET_F = ("de-DE-Wavenet-F", "de", "f", "Wavenet", "German female (alt2)")
    DE_NEURAL2_A = ("de-DE-Neural2-A", "de", "f", "Neural2", "German female (Neural2)")
    DE_NEURAL2_B = ("de-DE-Neural2-B", "de", "m", "Neural2", "German male (Neural2)")
    DE_NEURAL2_C = ("de-DE-Neural2-C", "de", "f", "Neural2", "German female (Neural2, alt)")
    DE_NEURAL2_D = ("de-DE-Neural2-D", "de", "m", "Neural2", "German male (Neural2, alt)")
    DE_NEURAL2_F = ("de-DE-Neural2-F", "de", "f", "Neural2", "German female (Neural2, alt2)")

    # Norwegian voices
    NB_WAVENET_A = ("nb-NO-Wavenet-A", "nb", "f", "Wavenet", "Norwegian female")
    NB_WAVENET_B = ("nb-NO-Wavenet-B", "nb", "m", "Wavenet", "Norwegian male")
    NB_WAVENET_C = ("nb-NO-Wavenet-C", "nb", "f", "Wavenet", "Norwegian female (alt)")
    NB_WAVENET_D = ("nb-NO-Wavenet-D", "nb", "m", "Wavenet", "Norwegian male (alt)")
    NB_WAVENET_E = ("nb-NO-Wavenet-E", "nb", "f", "Wavenet", "Norwegian female (alt2)")

    # Polish voices
    PL_WAVENET_A = ("pl-PL-Wavenet-A", "pl", "f", "Wavenet", "Polish female")
    PL_WAVENET_B = ("pl-PL-Wavenet-B", "pl", "m", "Wavenet", "Polish male")
    PL_WAVENET_C = ("pl-PL-Wavenet-C", "pl", "m", "Wavenet", "Polish male (alt)")
    PL_WAVENET_D = ("pl-PL-Wavenet-D", "pl", "f", "Wavenet", "Polish female (alt)")
    PL_WAVENET_E = ("pl-PL-Wavenet-E", "pl", "f", "Wavenet", "Polish female (alt2)")

    # Portuguese voices
    PT_WAVENET_A = ("pt-BR-Wavenet-A", "pt", "f", "Wavenet", "Portuguese (BR) female")
    PT_WAVENET_B = ("pt-BR-Wavenet-B", "pt", "m", "Wavenet", "Portuguese (BR) male")
    PT_WAVENET_C = ("pt-BR-Wavenet-C", "pt", "f", "Wavenet", "Portuguese (BR) female (alt)")
    PT_NEURAL2_A = ("pt-BR-Neural2-A", "pt", "f", "Neural2", "Portuguese (BR) female (Neural2)")
    PT_NEURAL2_B = ("pt-BR-Neural2-B", "pt", "m", "Neural2", "Portuguese (BR) male (Neural2)")
    PT_NEURAL2_C = (
        "pt-BR-Neural2-C",
        "pt",
        "f",
        "Neural2",
        "Portuguese (BR) female (Neural2, alt)",
    )

    # Romanian voices
    RO_WAVENET_A = ("ro-RO-Wavenet-A", "ro", "f", "Wavenet", "Romanian female")

    # Russian voices
    RU_WAVENET_A = ("ru-RU-Wavenet-A", "ru", "f", "Wavenet", "Russian female")
    RU_WAVENET_B = ("ru-RU-Wavenet-B", "ru", "m", "Wavenet", "Russian male")
    RU_WAVENET_C = ("ru-RU-Wavenet-C", "ru", "f", "Wavenet", "Russian female (alt)")
    RU_WAVENET_D = ("ru-RU-Wavenet-D", "ru", "m", "Wavenet", "Russian male (alt)")
    RU_WAVENET_E = ("ru-RU-Wavenet-E", "ru", "f", "Wavenet", "Russian female (alt2)")

    # Slovak voices
    SK_WAVENET_A = ("sk-SK-Wavenet-A", "sk", "f", "Wavenet", "Slovak female")

    # Swedish voices
    SV_WAVENET_A = ("sv-SE-Wavenet-A", "sv", "f", "Wavenet", "Swedish female")
    SV_WAVENET_B = ("sv-SE-Wavenet-B", "sv", "f", "Wavenet", "Swedish female (alt)")
    SV_WAVENET_C = ("sv-SE-Wavenet-C", "sv", "f", "Wavenet", "Swedish female (alt2)")
    SV_WAVENET_D = ("sv-SE-Wavenet-D", "sv", "m", "Wavenet", "Swedish male")
    SV_WAVENET_E = ("sv-SE-Wavenet-E", "sv", "m", "Wavenet", "Swedish male (alt)")

    # Tamil voices
    TA_WAVENET_A = ("ta-IN-Wavenet-A", "ta", "f", "Wavenet", "Tamil female")
    TA_WAVENET_B = ("ta-IN-Wavenet-B", "ta", "m", "Wavenet", "Tamil male")

    # Telugu voices
    TE_WAVENET_A = ("te-IN-Wavenet-A", "te", "f", "Wavenet", "Telugu female")
    TE_WAVENET_B = ("te-IN-Wavenet-B", "te", "m", "Wavenet", "Telugu male")

    # Thai voices
    TH_NEURAL2_C = ("th-TH-Neural2-C", "th", "f", "Neural2", "Thai female (Neural2)")

    # Turkish voices
    TR_WAVENET_A = ("tr-TR-Wavenet-A", "tr", "f", "Wavenet", "Turkish female")
    TR_WAVENET_B = ("tr-TR-Wavenet-B", "tr", "m", "Wavenet", "Turkish male")
    TR_WAVENET_C = ("tr-TR-Wavenet-C", "tr", "f", "Wavenet", "Turkish female (alt)")
    TR_WAVENET_D = ("tr-TR-Wavenet-D", "tr", "f", "Wavenet", "Turkish female (alt2)")
    TR_WAVENET_E = ("tr-TR-Wavenet-E", "tr", "m", "Wavenet", "Turkish male (alt)")

    # Ukrainian voices
    UK_WAVENET_A = ("uk-UA-Wavenet-A", "uk", "f", "Wavenet", "Ukrainian female")

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
