#!/usr/bin/python3
"""Type definitions for eSpeak-NG audio generation."""

from enum import Enum


class EspeakVoice(Enum):
    """
    Available eSpeak-NG voices with culturally appropriate names.

    Each voice has a language-specific name and gender. The value tuple contains:
    (language_code, gender, variant_number)

    Gender: 'm' for male, 'f' for female
    Variant: 1-4 for different voice characteristics
    """

    # Lithuanian voices
    ONA = ("lt", "f", 1)        # Female, variant 1
    JONAS = ("lt", "m", 1)      # Male, variant 1
    RUTA = ("lt", "f", 2)       # Female, variant 2

    # Chinese (Mandarin) voices
    MEI = ("zh", "f", 1)        # Female, variant 1
    WEI = ("zh", "m", 1)        # Male, variant 1
    LING = ("zh", "f", 2)       # Female, variant 2

    # Korean voices
    MINJI = ("ko", "f", 1)      # Female, variant 1
    JOON = ("ko", "m", 1)       # Male, variant 1
    SORA = ("ko", "f", 2)       # Female, variant 2

    # French voices
    CLAIRE = ("fr", "f", 1)     # Female, variant 1
    PIERRE = ("fr", "m", 1)     # Male, variant 1
    MARIE = ("fr", "f", 2)      # Female, variant 2

    # German voices
    ANNA = ("de", "f", 1)       # Female, variant 1
    HANS = ("de", "m", 1)       # Male, variant 1
    GRETA = ("de", "f", 2)      # Female, variant 2

    # Spanish voices
    SOFIA = ("es", "f", 1)      # Female, variant 1
    CARLOS = ("es", "m", 1)     # Male, variant 1
    ISABEL = ("es", "f", 2)     # Female, variant 2

    # Portuguese voices
    ANA = ("pt", "f", 1)        # Female, variant 1
    JOAO = ("pt", "m", 1)       # Male, variant 1
    MARIA = ("pt", "f", 2)      # Female, variant 2

    # Swahili voices
    AMANI = ("sw", "f", 1)      # Female, variant 1
    JABARI = ("sw", "m", 1)     # Male, variant 1
    ZARA = ("sw", "f", 2)       # Female, variant 2

    # Vietnamese voices
    LINH = ("vi", "f", 1)       # Female, variant 1
    MINH = ("vi", "m", 1)       # Male, variant 1
    HOA = ("vi", "f", 2)        # Female, variant 2

    @property
    def language_code(self) -> str:
        """Get the language code for this voice."""
        return self.value[0]

    @property
    def gender(self) -> str:
        """Get the gender for this voice ('m' or 'f')."""
        return self.value[1]

    @property
    def variant(self) -> int:
        """Get the variant number for this voice."""
        return self.value[2]

    @property
    def espeak_identifier(self) -> str:
        """
        Get the eSpeak-NG voice identifier.

        Format: {language}+{gender}{variant}
        Example: lt+f1 (Lithuanian, female, variant 1)
        """
        return f"{self.language_code}+{self.gender}{self.variant}"

    @classmethod
    def get_voices_for_language(cls, language_code: str):
        """Get all available voices for a specific language."""
        return [voice for voice in cls if voice.language_code == language_code]

    @classmethod
    def get_default_voices_for_language(cls, language_code: str):
        """Get default voices for a language (typically first 3 voices)."""
        voices = cls.get_voices_for_language(language_code)
        return voices[:3] if len(voices) >= 3 else voices


# Default voices for each language (3 per language)
DEFAULT_ESPEAK_VOICES = {
    "lt": [EspeakVoice.ONA, EspeakVoice.JONAS, EspeakVoice.RUTA],
    "zh": [EspeakVoice.MEI, EspeakVoice.WEI, EspeakVoice.LING],
    "ko": [EspeakVoice.MINJI, EspeakVoice.JOON, EspeakVoice.SORA],
    "fr": [EspeakVoice.CLAIRE, EspeakVoice.PIERRE, EspeakVoice.MARIE],
    "de": [EspeakVoice.ANNA, EspeakVoice.HANS, EspeakVoice.GRETA],
    "es": [EspeakVoice.SOFIA, EspeakVoice.CARLOS, EspeakVoice.ISABEL],
    "pt": [EspeakVoice.ANA, EspeakVoice.JOAO, EspeakVoice.MARIA],
    "sw": [EspeakVoice.AMANI, EspeakVoice.JABARI, EspeakVoice.ZARA],
    "vi": [EspeakVoice.LINH, EspeakVoice.MINH, EspeakVoice.HOA],
}
