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
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
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

    # Amharic voices
    AMEHA = ("am-ET-AmehaNeural", "am", "m", "Amharic male")
    MEKDES = ("am-ET-MekdesNeural", "am", "f", "Amharic female")

    # Arabic voices
    SALMA = ("ar-EG-SalmaNeural", "ar", "f", "Arabic (Egypt) female")
    SHAKIR = ("ar-EG-ShakirNeural", "ar", "m", "Arabic (Egypt) male")
    ZARIYAH = ("ar-SA-ZariyahNeural", "ar", "f", "Arabic (Saudi) female")
    HAMED = ("ar-SA-HamedNeural", "ar", "m", "Arabic (Saudi) male")

    # Azerbaijani voices
    BANU = ("az-AZ-BanuNeural", "az", "f", "Azerbaijani female")
    BABEK = ("az-AZ-BabekNeural", "az", "m", "Azerbaijani male")

    # Bengali voices
    NABANITA = ("bn-IN-NabanitaNeural", "bn", "f", "Bengali female")
    BASHKAR = ("bn-IN-BashkarNeural", "bn", "m", "Bengali male")

    # Bulgarian voices
    KALINA = ("bg-BG-KalinaNeural", "bg", "f", "Bulgarian female")
    BORISLAV = ("bg-BG-BorislavNeural", "bg", "m", "Bulgarian male")

    # Catalan voices
    JOANA = ("ca-ES-JoanaNeural", "ca", "f", "Catalan female")
    ENRIC = ("ca-ES-EnricNeural", "ca", "m", "Catalan male")

    # Croatian voices
    GABRIJELA = ("hr-HR-GabrijelaNeural", "hr", "f", "Croatian female")
    SRECKO = ("hr-HR-SreckoNeural", "hr", "m", "Croatian male")

    # Czech voices
    VLASTA = ("cs-CZ-VlastaNeural", "cs", "f", "Czech female")
    ANTONIN = ("cs-CZ-AntoninNeural", "cs", "m", "Czech male")

    # Danish voices
    CHRISTEL = ("da-DK-ChristelNeural", "da", "f", "Danish female")
    JEPPE = ("da-DK-JeppeNeural", "da", "m", "Danish male")

    # Dutch voices
    COLETTE = ("nl-NL-ColetteNeural", "nl", "f", "Dutch female")
    FENNA = ("nl-NL-FennaNeural", "nl", "f", "Dutch female (alt)")
    MAARTEN = ("nl-NL-MaartenNeural", "nl", "m", "Dutch male")
    DENA = ("nl-BE-DenaNeural", "nl", "f", "Dutch (Belgian) female")
    ARNAUD = ("nl-BE-ArnaudNeural", "nl", "m", "Dutch (Belgian) male")

    # English voices
    AVA = ("en-US-AvaNeural", "en", "f", "English (US) female")
    ANDREW = ("en-US-AndrewNeural", "en", "m", "English (US) male")
    EMMA = ("en-US-EmmaNeural", "en", "f", "English (US) female (alt)")
    BRIAN = ("en-US-BrianNeural", "en", "m", "English (US) male (alt)")
    JENNY = ("en-US-JennyNeural", "en", "f", "English (US) female (alt2)")
    ARIA = ("en-US-AriaNeural", "en", "f", "English (US) female (alt3)")
    DAVIS = ("en-US-DavisNeural", "en", "m", "English (US) male (alt2)")
    SONIA = ("en-GB-SoniaNeural", "en", "f", "English (GB) female")
    RYAN = ("en-GB-RyanNeural", "en", "m", "English (GB) male")
    LIBBY = ("en-GB-LibbyNeural", "en", "f", "English (GB) female (alt)")
    NATASHA = ("en-AU-NatashaNeural", "en", "f", "English (AU) female")
    WILLIAM = ("en-AU-WilliamNeural", "en", "m", "English (AU) male")
    NEERJA = ("en-IN-NeerjaNeural", "en", "f", "English (IN) female")

    # Estonian voices
    ANU = ("et-EE-AnuNeural", "et", "f", "Estonian female")
    KERT = ("et-EE-KertNeural", "et", "m", "Estonian male")

    # Filipino voices
    ROSA = ("fil-PH-RosaNeural", "tl", "f", "Filipino female")
    ANGELO = ("fil-PH-AngeloNeural", "tl", "m", "Filipino male")

    # Finnish voices
    NOORA = ("fi-FI-NooraNeural", "fi", "f", "Finnish female")
    HARRI = ("fi-FI-HarriNeural", "fi", "m", "Finnish male")

    # Greek voices
    ATHINA = ("el-GR-AthinaNeural", "el", "f", "Greek female")
    NESTORAS = ("el-GR-NestorasNeural", "el", "m", "Greek male")

    # Hebrew voices
    HILA = ("he-IL-HilaNeural", "he", "f", "Hebrew female")
    AVRI = ("he-IL-AvriNeural", "he", "m", "Hebrew male")

    # Hindi voices
    SWARA = ("hi-IN-SwaraNeural", "hi", "f", "Hindi female")
    MADHUR = ("hi-IN-MadhurNeural", "hi", "m", "Hindi male")

    # Hungarian voices
    NOEMI = ("hu-HU-NoemiNeural", "hu", "f", "Hungarian female")
    TAMAS = ("hu-HU-TamasNeural", "hu", "m", "Hungarian male")

    # Icelandic voices
    GUDRUN = ("is-IS-GudrunNeural", "is", "f", "Icelandic female")
    GUNNAR = ("is-IS-GunnarNeural", "is", "m", "Icelandic male")

    # Indonesian voices
    ARDI = ("id-ID-ArdiNeural", "id", "m", "Indonesian male")
    GADIS = ("id-ID-GadisNeural", "id", "f", "Indonesian female")

    # Irish voices
    EMILY = ("ga-IE-EmilyNeural", "ga", "f", "Irish female")
    COLM = ("ga-IE-ColmNeural", "ga", "m", "Irish male")

    # Lithuanian voices
    ONA = ("lt-LT-OnaNeural", "lt", "f", "Lithuanian female")
    LEONAS = ("lt-LT-LeonasNeural", "lt", "m", "Lithuanian male")

    # Chinese (Mandarin) voices
    XIAOXIAO = ("zh-CN-XiaoxiaoNeural", "zh", "f", "Chinese female (warm)")
    YUNXI = ("zh-CN-YunxiNeural", "zh", "m", "Chinese male (cheerful)")
    XIAOYI = ("zh-CN-XiaoyiNeural", "zh", "f", "Chinese female (lively)")
    YUNJIAN = ("zh-CN-YunjianNeural", "zh", "m", "Chinese male (sports)")
    XIAOYOU = ("zh-CN-XiaoyouNeural", "zh", "f", "Chinese female (child)")
    YUNFAN = ("zh-CN-YunfanNeural", "zh", "m", "Chinese male (calm)")

    # Spanish voices
    ELVIRA = ("es-ES-ElviraNeural", "es", "f", "Spanish (ES) female")
    ALVARO = ("es-ES-AlvaroNeural", "es", "m", "Spanish (ES) male")
    DALIA = ("es-MX-DaliaNeural", "es", "f", "Spanish (MX) female")
    JORGE = ("es-MX-JorgeNeural", "es", "m", "Spanish (MX) male")
    XIMENA = ("es-MX-XimenaNeural", "es", "f", "Spanish (MX) female (alt)")

    # French voices
    DENISE = ("fr-FR-DeniseNeural", "fr", "f", "French female")
    HENRI = ("fr-FR-HenriNeural", "fr", "m", "French male")
    VIVIENNE = ("fr-FR-VivienneNeural", "fr", "f", "French female (alt)")
    REMY = ("fr-FR-RemyNeural", "fr", "m", "French male (alt)")
    SYLVIE = ("fr-CA-SylvieNeural", "fr", "f", "French (CA) female")
    ANTOINE = ("fr-CA-AntoineNeural", "fr", "m", "French (CA) male")

    # Georgian voices
    EKA = ("ka-GE-EkaNeural", "ka", "f", "Georgian female")
    GIORGI = ("ka-GE-GiorgiNeural", "ka", "m", "Georgian male")

    # Italian voices
    ISABELLA = ("it-IT-IsabellaNeural", "it", "f", "Italian female")
    DIEGO = ("it-IT-DiegoNeural", "it", "m", "Italian male")
    ELSA = ("it-IT-ElsaNeural", "it", "f", "Italian female (alt)")

    # Japanese voices
    NANAMI = ("ja-JP-NanamiNeural", "ja", "f", "Japanese female")
    KEITA = ("ja-JP-KeitaNeural", "ja", "m", "Japanese male")
    AOI = ("ja-JP-AoiNeural", "ja", "f", "Japanese female (alt)")
    NAOKI = ("ja-JP-NaokiNeural", "ja", "m", "Japanese male (alt)")

    # Kannada voices
    SAPNA = ("kn-IN-SapnaNeural", "kn", "f", "Kannada female")
    GAGAN = ("kn-IN-GaganNeural", "kn", "m", "Kannada male")

    # Korean voices
    SUNHI = ("ko-KR-SunHiNeural", "ko", "f", "Korean female")
    INJOONG = ("ko-KR-InJoonNeural", "ko", "m", "Korean male")
    HYUNSU = ("ko-KR-HyunsuNeural", "ko", "m", "Korean male (alt)")

    # Latvian voices
    EVERITA = ("lv-LV-EveritaNeural", "lv", "f", "Latvian female")
    NILS = ("lv-LV-NilsNeural", "lv", "m", "Latvian male")

    # Malayalam voices
    SOBHANA = ("ml-IN-SobhanaNeural", "ml", "f", "Malayalam female")
    MIDHUN = ("ml-IN-MidhunNeural", "ml", "m", "Malayalam male")

    # Maltese voices
    GRACE = ("mt-MT-GraceNeural", "mt", "f", "Maltese female")
    JOSEPH = ("mt-MT-JosephNeural", "mt", "m", "Maltese male")

    # German voices
    KATJA = ("de-DE-KatjaNeural", "de", "f", "German female")
    CONRAD = ("de-DE-ConradNeural", "de", "m", "German male")
    AMALA = ("de-DE-AmalaNeural", "de", "f", "German female (alt)")
    BERND = ("de-DE-BerndNeural", "de", "m", "German male (alt)")
    INGRID = ("de-AT-IngridNeural", "de", "f", "German (AT) female")
    JONAS = ("de-AT-JonasNeural", "de", "m", "German (AT) male")

    # Norwegian voices
    PERNILLE = ("nb-NO-PernilleNeural", "nb", "f", "Norwegian female")
    FINN = ("nb-NO-FinnNeural", "nb", "m", "Norwegian male")

    # Persian voices
    DILARA = ("fa-IR-DilaraNeural", "fa", "f", "Persian female")
    FARID = ("fa-IR-FaridNeural", "fa", "m", "Persian male")

    # Polish voices
    ZOFIA = ("pl-PL-ZofiaNeural", "pl", "f", "Polish female")
    MAREK = ("pl-PL-MarekNeural", "pl", "m", "Polish male")
    AGNIESZKA = ("pl-PL-AgnieszkaNeural", "pl", "f", "Polish female (alt)")

    # Portuguese voices
    FRANCISCA = ("pt-BR-FranciscaNeural", "pt", "f", "Portuguese (BR) female")
    ANTONIO = ("pt-BR-AntonioNeural", "pt", "m", "Portuguese (BR) male")
    THALITA = ("pt-BR-ThalitaNeural", "pt", "f", "Portuguese (BR) female (alt)")
    RAQUEL = ("pt-PT-RaquelNeural", "pt", "f", "Portuguese (PT) female")
    DUARTE = ("pt-PT-DuarteNeural", "pt", "m", "Portuguese (PT) male")

    # Romanian voices
    ALINA = ("ro-RO-AlinaNeural", "ro", "f", "Romanian female")
    EMIL = ("ro-RO-EmilNeural", "ro", "m", "Romanian male")

    # Russian voices
    SVETLANA = ("ru-RU-SvetlanaNeural", "ru", "f", "Russian female")
    DMITRY = ("ru-RU-DmitryNeural", "ru", "m", "Russian male")
    DARIYA = ("ru-RU-DariyaNeural", "ru", "f", "Russian female (alt)")

    # Sinhala voices
    THILINI = ("si-LK-ThiliniNeural", "si", "f", "Sinhala female")
    SAMEERA = ("si-LK-SameeraNeural", "si", "m", "Sinhala male")

    # Slovak voices
    VIKTORIA = ("sk-SK-ViktoriaNeural", "sk", "f", "Slovak female")
    LUKAS = ("sk-SK-LukasNeural", "sk", "m", "Slovak male")

    # Slovenian voices
    PETRA = ("sl-SI-PetraNeural", "sl", "f", "Slovenian female")
    ROK = ("sl-SI-RokNeural", "sl", "m", "Slovenian male")

    # Swahili voices
    ZURI = ("sw-KE-ZuriNeural", "sw", "f", "Swahili female")
    RAFIKI = ("sw-KE-RafikiNeural", "sw", "m", "Swahili male")

    # Swedish voices
    SOFIE = ("sv-SE-SofieNeural", "sv", "f", "Swedish female")
    MATTIAS = ("sv-SE-MattiasNeural", "sv", "m", "Swedish male")
    HILLEVI = ("sv-SE-HilleviNeural", "sv", "f", "Swedish female (alt)")

    # Tamil voices
    PALLAVI = ("ta-IN-PallaviNeural", "ta", "f", "Tamil female")
    VALLUVAR = ("ta-IN-ValluvarNeural", "ta", "m", "Tamil male")

    # Telugu voices
    SHRUTI = ("te-IN-ShrutiNeural", "te", "f", "Telugu female")
    MOHAN = ("te-IN-MohanNeural", "te", "m", "Telugu male")

    # Thai voices
    PREMWADEE = ("th-TH-PremwadeeNeural", "th", "f", "Thai female")
    NIWAT = ("th-TH-NiwatNeural", "th", "m", "Thai male")

    # Turkish voices
    EMEL = ("tr-TR-EmelNeural", "tr", "f", "Turkish female")
    AHMET = ("tr-TR-AhmetNeural", "tr", "m", "Turkish male")

    # Ukrainian voices
    POLINA = ("uk-UA-PolinaNeural", "uk", "f", "Ukrainian female")
    OSTAP = ("uk-UA-OstapNeural", "uk", "m", "Ukrainian male")

    # Vietnamese voices
    HOAIMY = ("vi-VN-HoaiMyNeural", "vi", "f", "Vietnamese female")
    NAMMINH = ("vi-VN-NamMinhNeural", "vi", "m", "Vietnamese male")

    # Zulu voices
    THANDO = ("zu-ZA-ThandoNeural", "zu", "f", "Zulu female")
    THEMBA = ("zu-ZA-ThembaNeural", "zu", "m", "Zulu male")

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
    from clients.keys import assert_credential_reads_enabled

    assert_credential_reads_enabled("azure_tts")

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
