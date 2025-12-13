#!/usr/bin/python3
"""Type definitions for eSpeak-NG audio generation."""

from enum import Enum

# Mapping of our language codes to eSpeak-NG primary language codes
# Some languages need the primary code (not alias) for variant notation to work
# Based on: espeak-ng --voices output
ESPEAK_LANGUAGE_CODES = {
    "zh": "cmn",      # Chinese (Mandarin) - primary code is 'cmn', 'zh' is alias
    "ko": "ko",       # Korean
    "lt": "lt",       # Lithuanian
    "vi": "vi",       # Vietnamese (Northern)
    "sw": "sw",       # Swahili
    "fr": "fr-fr",    # French (France)
    "de": "de",       # German
    "es": "es",       # Spanish (Spain)
    "pt": "pt",       # Portuguese (Portugal)
}


class EspeakVoice(Enum):
    """
    Available eSpeak-NG voices with culturally appropriate names.

    Each voice has a language-specific name and gender. The value tuple contains:
    - For regular eSpeak voices: (language_code, gender, variant_number)
    - For MBROLA voices: (language_code, gender, mbrola_voice_code)

    Gender: 'm' for male, 'f' for female
    Variant: 1-4 for different voice characteristics (regular eSpeak only)
    MBROLA codes: e.g., "mb-fr1", "mb-de2" (high-quality diphone synthesis)
    """

    # Lithuanian voices (2F/2M regular + 2M MBROLA)
    ONA = ("lt", "f", 1)        # Female, variant 1
    JONAS = ("lt", "m", 1)      # Male, variant 1
    RUTA = ("lt", "f", 2)       # Female, variant 2
    TOMAS = ("lt", "m", 2)      # Male, variant 2
    VYTAUTAS = ("lt", "m", "mb-lt1")  # MBROLA Male, high quality
    DARIUS = ("lt", "m", "mb-lt2")    # MBROLA Male, high quality

    # Chinese (Mandarin) voices (2F/2M regular + 1F MBROLA)
    MEI = ("zh", "f", 1)        # Female, variant 1
    WEI = ("zh", "m", 1)        # Male, variant 1
    LING = ("zh", "f", 2)       # Female, variant 2
    JUN = ("zh", "m", 2)        # Male, variant 2
    XIAOMEI = ("zh", "f", "mb-cn1")  # MBROLA Female, high quality

    # Korean voices (2F/2M regular + 1M MBROLA)
    MINJI = ("ko", "f", 1)      # Female, variant 1
    JOON = ("ko", "m", 1)       # Male, variant 1
    SORA = ("ko", "f", 2)       # Female, variant 2
    MINSU = ("ko", "m", 2)      # Male, variant 2
    JIHOON = ("ko", "m", "mb-hn1")   # MBROLA Male, high quality

    # French voices (2F/2M regular + 2F/2M MBROLA)
    CLAIRE = ("fr", "f", 1)     # Female, variant 1
    PIERRE = ("fr", "m", 1)     # Male, variant 1
    MARIE = ("fr", "f", 2)      # Female, variant 2
    LUC = ("fr", "m", 2)        # Male, variant 2
    CAMILLE = ("fr", "f", "mb-fr2")  # MBROLA Female, high quality
    JACQUES = ("fr", "m", "mb-fr1")  # MBROLA Male, high quality
    SOPHIE = ("fr", "f", "mb-fr4")   # MBROLA Female, high quality
    BERNARD = ("fr", "m", "mb-fr3")  # MBROLA Male, high quality

    # German voices (2F/2M regular + 2F/2M MBROLA)
    ANNA = ("de", "f", 1)       # Female, variant 1
    HANS = ("de", "m", 1)       # Male, variant 1
    GRETA = ("de", "f", 2)      # Female, variant 2
    KARL = ("de", "m", 2)       # Male, variant 2
    PETRA = ("de", "f", "mb-de1")    # MBROLA Female, high quality
    KLAUS = ("de", "m", "mb-de2")    # MBROLA Male, high quality
    BIRGIT = ("de", "f", "mb-de5")   # MBROLA Female, high quality
    STEFAN = ("de", "m", "mb-de4")   # MBROLA Male, high quality

    # Spanish voices (2F/2M regular + 1F/2M MBROLA)
    SOFIA = ("es", "f", 1)      # Female, variant 1
    CARLOS = ("es", "m", 1)     # Male, variant 1
    ISABEL = ("es", "f", 2)     # Female, variant 2
    DIEGO = ("es", "m", 2)      # Male, variant 2
    CARMEN = ("es", "f", "mb-es3")   # MBROLA Female, high quality
    RAUL = ("es", "m", "mb-es1")     # MBROLA Male, high quality
    MIGUEL = ("es", "m", "mb-es2")   # MBROLA Male, high quality

    # Portuguese voices (2F/2M regular + 1F/2M MBROLA)
    ANA = ("pt", "f", 1)        # Female, variant 1
    JOAO = ("pt", "m", 1)       # Male, variant 1
    MARIA = ("pt", "f", 2)      # Female, variant 2
    PEDRO = ("pt", "m", 2)      # Male, variant 2
    GABRIELA = ("pt", "f", "mb-br4")  # MBROLA Female (Brazilian), high quality
    RICARDO = ("pt", "m", "mb-br1")   # MBROLA Male (Brazilian), high quality
    FERNANDO = ("pt", "m", "mb-br3")  # MBROLA Male (Brazilian), high quality

    # Swahili voices (2F/2M regular - no MBROLA available)
    AMANI = ("sw", "f", 1)      # Female, variant 1
    JABARI = ("sw", "m", 1)     # Male, variant 1
    ZARA = ("sw", "f", 2)       # Female, variant 2
    KIANO = ("sw", "m", 2)      # Male, variant 2

    # Vietnamese voices (2F/2M regular - no MBROLA available)
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
    def is_mbrola(self) -> bool:
        """Check if this is a MBROLA voice."""
        return isinstance(self.value[2], str) and self.value[2].startswith("mb-")

    @property
    def variant(self) -> int:
        """Get the variant number for this voice (regular eSpeak only)."""
        if self.is_mbrola:
            return 0  # MBROLA voices don't have variants
        return self.value[2]

    @property
    def mbrola_code(self) -> str:
        """Get the MBROLA voice code (MBROLA voices only)."""
        if self.is_mbrola:
            return self.value[2]
        return None

    @property
    def espeak_identifier(self) -> str:
        """
        Get the eSpeak-NG voice identifier.

        For regular eSpeak voices:
          Format: {language}+{gender}{variant}
          Example: cmn+f1 (Chinese Mandarin, female, variant 1)
                   lt+f1 (Lithuanian, female, variant 1)

        For MBROLA voices:
          Format: {mbrola_code}
          Example: mb-fr1 (MBROLA French male voice 1)
                   mb-de2 (MBROLA German male voice 2)

        Note: For regular voices, uses primary eSpeak language codes (e.g., 'cmn' not 'zh')
        because variants only work with primary codes, not aliases.
        """
        if self.is_mbrola:
            return self.mbrola_code

        espeak_lang = ESPEAK_LANGUAGE_CODES.get(self.language_code, self.language_code)
        return f"{espeak_lang}+{self.gender}{self.variant}"

    @classmethod
    def get_voices_for_language(cls, language_code: str):
        """Get all available voices for a specific language."""
        return [voice for voice in cls if voice.language_code == language_code]

    @classmethod
    def get_default_voices_for_language(cls, language_code: str):
        """Get default voices for a language (all voices including MBROLA)."""
        return cls.get_voices_for_language(language_code)

    @classmethod
    def get_mbrola_voices_for_language(cls, language_code: str):
        """Get only MBROLA voices for a specific language."""
        return [voice for voice in cls if voice.language_code == language_code and voice.is_mbrola]

    @classmethod
    def get_regular_voices_for_language(cls, language_code: str):
        """Get only regular eSpeak voices (non-MBROLA) for a specific language."""
        return [voice for voice in cls if voice.language_code == language_code and not voice.is_mbrola]


# Default voices for each language (regular eSpeak voices: 2F/2M per language)
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

# MBROLA voices for each language (high-quality diphone synthesis)
# Note: Vietnamese and Swahili do not have MBROLA voices available
MBROLA_VOICES = {
    "lt": [EspeakVoice.VYTAUTAS, EspeakVoice.DARIUS],
    "zh": [EspeakVoice.XIAOMEI],
    "ko": [EspeakVoice.JIHOON],
    "fr": [EspeakVoice.CAMILLE, EspeakVoice.JACQUES, EspeakVoice.SOPHIE, EspeakVoice.BERNARD],
    "de": [EspeakVoice.PETRA, EspeakVoice.KLAUS, EspeakVoice.BIRGIT, EspeakVoice.STEFAN],
    "es": [EspeakVoice.CARMEN, EspeakVoice.RAUL, EspeakVoice.MIGUEL],
    "pt": [EspeakVoice.GABRIELA, EspeakVoice.RICARDO, EspeakVoice.FERNANDO],
    "sw": [],  # No MBROLA voices available
    "vi": [],  # No MBROLA voices available
}

# Recommended high-quality voices (mix of MBROLA where available, regular eSpeak otherwise)
RECOMMENDED_VOICES = {
    "lt": [EspeakVoice.VYTAUTAS, EspeakVoice.DARIUS, EspeakVoice.ONA, EspeakVoice.RUTA],
    "zh": [EspeakVoice.XIAOMEI, EspeakVoice.MEI, EspeakVoice.WEI, EspeakVoice.LING],
    "ko": [EspeakVoice.JIHOON, EspeakVoice.MINJI, EspeakVoice.JOON, EspeakVoice.SORA],
    "fr": [EspeakVoice.CAMILLE, EspeakVoice.JACQUES, EspeakVoice.SOPHIE, EspeakVoice.BERNARD],
    "de": [EspeakVoice.PETRA, EspeakVoice.KLAUS, EspeakVoice.BIRGIT, EspeakVoice.STEFAN],
    "es": [EspeakVoice.CARMEN, EspeakVoice.RAUL, EspeakVoice.MIGUEL, EspeakVoice.SOFIA],
    "pt": [EspeakVoice.GABRIELA, EspeakVoice.RICARDO, EspeakVoice.FERNANDO, EspeakVoice.MARIA],
    "sw": [EspeakVoice.AMANI, EspeakVoice.JABARI, EspeakVoice.ZARA, EspeakVoice.KIANO],
    "vi": [EspeakVoice.LINH, EspeakVoice.MINH, EspeakVoice.HOA, EspeakVoice.TUAN],
}
