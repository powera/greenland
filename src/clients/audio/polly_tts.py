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
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
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

    # Arabic voices
    HALA = ("Hala", "ar", "f", "neural", "Arabic (Gulf) female")
    ZAYD = ("Zayd", "ar", "m", "neural", "Arabic (Gulf) male")

    # Catalan voices
    ARLET = ("Arlet", "ca", "f", "neural", "Catalan female")

    # Czech voices
    JITKA = ("Jitka", "cs", "f", "neural", "Czech female")

    # Chinese (Mandarin) voices
    ZHIYU = ("Zhiyu", "zh", "f", "neural", "Chinese Mandarin female")

    # Chinese (Cantonese) voices
    HIUJIN = ("Hiujin", "yue", "f", "neural", "Chinese Cantonese female")

    # Danish voices
    NAJA = ("Naja", "da", "f", "neural", "Danish female")
    MADS = ("Mads", "da", "m", "neural", "Danish male")
    SOFIE = ("Sofie", "da", "f", "neural", "Danish female (alt)")

    # Dutch voices
    LAURA = ("Laura", "nl", "f", "neural", "Dutch (NL) female")
    RUBEN = ("Ruben", "nl", "m", "neural", "Dutch (NL) male")
    LISA = ("Lisa", "nl", "f", "neural", "Dutch (BE) female")

    # English voices
    DANIELLE = ("Danielle", "en", "f", "neural", "English (US) female")
    GREGORY = ("Gregory", "en", "m", "neural", "English (US) male")
    JOANNA = ("Joanna", "en", "f", "neural", "English (US) female")
    MATTHEW = ("Matthew", "en", "m", "neural", "English (US) male")
    RUTH = ("Ruth", "en", "f", "neural", "English (US) female")
    STEPHEN = ("Stephen", "en", "m", "neural", "English (US) male")
    AMY = ("Amy", "en", "f", "neural", "English (GB) female")
    EMMA = ("Emma", "en", "f", "neural", "English (GB) female")
    BRIAN = ("Brian", "en", "m", "neural", "English (GB) male")
    ARTHUR = ("Arthur", "en", "m", "neural", "English (GB) male")
    NICOLE = ("Nicole", "en", "f", "neural", "English (AU) female")
    RUSSELL = ("Russell", "en", "m", "neural", "English (AU) male")
    ADITI = ("Aditi", "en", "f", "neural", "English (IN) female")
    KAJAL_EN = ("Kajal", "en", "f", "neural", "English (IN) female (alt)")

    # Finnish voices
    SUVI = ("Suvi", "fi", "f", "neural", "Finnish female")

    # Spanish voices
    LUPE = ("Lupe", "es", "f", "neural", "Spanish (US) female")
    MIGUEL = ("Miguel", "es", "m", "neural", "Spanish (US) male")
    MIA = ("Mia", "es", "f", "neural", "Spanish (MX) female")
    ANDRES = ("Andres", "es", "m", "neural", "Spanish (MX) male")
    LUCIA = ("Lucia", "es", "f", "neural", "Spanish (ES) female")
    SERGIO = ("Sergio", "es", "m", "neural", "Spanish (ES) male")

    # French voices
    LEA = ("Lea", "fr", "f", "neural", "French (FR) female")
    REMI = ("Remi", "fr", "m", "neural", "French (FR) male")
    GABRIELLE = ("Gabrielle", "fr", "f", "neural", "French (CA) female")
    LIAM = ("Liam", "fr", "m", "neural", "French (CA) male")
    ISABELLE = ("Isabelle", "fr", "f", "neural", "French (BE) female")

    # Hindi voices
    KAJAL = ("Kajal", "hi", "f", "neural", "Hindi female")

    # Icelandic voices
    DORA = ("Dóra", "is", "f", "neural", "Icelandic female")
    KARL = ("Karl", "is", "m", "neural", "Icelandic male")

    # Italian voices
    BIANCA = ("Bianca", "it", "f", "neural", "Italian female")
    GIORGIO = ("Giorgio", "it", "m", "neural", "Italian male")

    # Japanese voices
    KAZUHA = ("Kazuha", "ja", "f", "neural", "Japanese female")
    TOMOKO = ("Tomoko", "ja", "f", "neural", "Japanese female (alt)")

    # Korean voices
    SEOYEON = ("Seoyeon", "ko", "f", "neural", "Korean female")
    JIHYE = ("Jihye", "ko", "f", "neural", "Korean female (alt)")

    # German voices
    VICKI = ("Vicki", "de", "f", "neural", "German (DE) female")
    DANIEL = ("Daniel", "de", "m", "neural", "German (DE) male")
    HANNAH = ("Hannah", "de", "f", "neural", "German (AT) female")
    SABRINA = ("Sabrina", "de", "f", "neural", "German (CH) female")

    # Norwegian voices
    IDA = ("Ida", "nb", "f", "neural", "Norwegian female")

    # Polish voices
    EWA = ("Ewa", "pl", "f", "neural", "Polish female")
    OLA = ("Ola", "pl", "f", "neural", "Polish female (alt)")

    # Portuguese voices
    CAMILA = ("Camila", "pt", "f", "neural", "Portuguese (BR) female")
    RICARDO = ("Ricardo", "pt", "m", "neural", "Portuguese (BR) male")
    THIAGO = ("Thiago", "pt", "m", "neural", "Portuguese (BR) male (alt)")
    INES = ("Inês", "pt", "f", "neural", "Portuguese (PT) female")

    # Swedish voices
    ELIN = ("Elin", "sv", "f", "neural", "Swedish female")

    # Turkish voices
    BURCU = ("Burcu", "tr", "f", "neural", "Turkish female")

    # Vietnamese voices
    # (Polly does not have Vietnamese neural voices as of 2026)

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
    "ar": "ar-AE",
    "ca": "ca-ES",
    "cs": "cs-CZ",
    "da": "da-DK",
    "de": "de-DE",
    "en": "en-US",
    "es": "es-ES",
    "fi": "fi-FI",
    "fr": "fr-FR",
    "hi": "hi-IN",
    "is": "is-IS",
    "it": "it-IT",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "nb": "nb-NO",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "pt": "pt-BR",
    "sv": "sv-SE",
    "tr": "tr-TR",
    "yue": "yue-CN",
    "zh": "cmn-CN",
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
