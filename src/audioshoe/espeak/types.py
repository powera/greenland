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

    # Lithuanian voices (2F/2M)
    ONA = ("lt", "f", 1)        # Female, variant 1
    JONAS = ("lt", "m", 1)      # Male, variant 1
    RUTA = ("lt", "f", 2)       # Female, variant 2
    TOMAS = ("lt", "m", 2)      # Male, variant 2

    # Chinese (Mandarin) voices (2F/2M)
    MEI = ("zh", "f", 1)        # Female, variant 1
    WEI = ("zh", "m", 1)        # Male, variant 1
    LING = ("zh", "f", 2)       # Female, variant 2
    JUN = ("zh", "m", 2)        # Male, variant 2

    # Korean voices (2F/2M)
    MINJI = ("ko", "f", 1)      # Female, variant 1
    JOON = ("ko", "m", 1)       # Male, variant 1
    SORA = ("ko", "f", 2)       # Female, variant 2
    MINSU = ("ko", "m", 2)      # Male, variant 2

    # French voices (2F/2M)
    CLAIRE = ("fr", "f", 1)     # Female, variant 1
    PIERRE = ("fr", "m", 1)     # Male, variant 1
    MARIE = ("fr", "f", 2)      # Female, variant 2
    LUC = ("fr", "m", 2)        # Male, variant 2

    # German voices (2F/2M)
    ANNA = ("de", "f", 1)       # Female, variant 1
    HANS = ("de", "m", 1)       # Male, variant 1
    GRETA = ("de", "f", 2)      # Female, variant 2
    KARL = ("de", "m", 2)       # Male, variant 2

    # Spanish voices (2F/2M)
    SOFIA = ("es", "f", 1)      # Female, variant 1
    CARLOS = ("es", "m", 1)     # Male, variant 1
    ISABEL = ("es", "f", 2)     # Female, variant 2
    DIEGO = ("es", "m", 2)      # Male, variant 2

    # Portuguese voices (2F/2M)
    ANA = ("pt", "f", 1)        # Female, variant 1
    JOAO = ("pt", "m", 1)       # Male, variant 1
    MARIA = ("pt", "f", 2)      # Female, variant 2
    PEDRO = ("pt", "m", 2)      # Male, variant 2

    # Swahili voices (2F/2M)
    AMANI = ("sw", "f", 1)      # Female, variant 1
    JABARI = ("sw", "m", 1)     # Male, variant 1
    ZARA = ("sw", "f", 2)       # Female, variant 2
    KIANO = ("sw", "m", 2)      # Male, variant 2

    # Vietnamese voices (2F/2M)
    LINH = ("vi", "f", 1)       # Female, variant 1
    MINH = ("vi", "m", 1)       # Male, variant 1
    HOA = ("vi", "f", 2)        # Female, variant 2
    TUAN = ("vi", "m", 2)       # Male, variant 2

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
        """Get default voices for a language (all 4 voices: 2F/2M)."""
        return cls.get_voices_for_language(language_code)


# Default voices for each language (4 per language: 2 female, 2 male)
DEFAULT_ESPEAK_VOICES = {
    "lt": [EspeakVoice.ONA, EspeakVoice.JONAS, EspeakVoice.RUTA, EspeakVoice.TOMAS],
    "zh": [EspeakVoice.MEI, EspeakVoice.WEI, EspeakVoice.LING, EspeakVoice.JUN],
    "ko": [EspeakVoice.MINJI, EspeakVoice.JOON, EspeakVoice.SORA, EspeakVoice.MINSU],
    "fr": [EspeakVoice.CLAIRE, EspeakVoice.PIERRE, EspeakVoice.MARIE, EspeakVoice.LUC],
    "de": [EspeakVoice.ANNA, EspeakVoice.HANS, EspeakVoice.GRETA, EspeakVoice.KARL],
    "es": [EspeakVoice.SOFIA, EspeakVoice.CARLOS, EspeakVoice.ISABEL, EspeakVoice.DIEGO],
    "pt": [EspeakVoice.ANA, EspeakVoice.JOAO, EspeakVoice.MARIA, EspeakVoice.PEDRO],
    "sw": [EspeakVoice.AMANI, EspeakVoice.JABARI, EspeakVoice.ZARA, EspeakVoice.KIANO],
    "vi": [EspeakVoice.LINH, EspeakVoice.MINH, EspeakVoice.HOA, EspeakVoice.TUAN],
}
