#!/usr/bin/python3
"""Type definitions for Piper TTS audio generation."""

from enum import Enum

# Mapping of our language codes to Piper language/region codes
PIPER_LANGUAGE_CODES = {
    "zh": "zh_CN",    # Chinese (Mandarin)
    "ko": "ko_KR",    # Korean
    "lt": "lt_LT",    # Lithuanian
    "vi": "vi_VN",    # Vietnamese
    "sw": "sw_CD",    # Swahili
    "fr": "fr_FR",    # French (France)
    "de": "de_DE",    # German
    "es": "es_ES",    # Spanish (Spain)
    "pt": "pt_PT",    # Portuguese (Portugal)
}


class PiperVoice(Enum):
    """
    Available Piper TTS voices with gender-based naming.

    Each voice has a simplified name for UI display. The value tuple contains:
    - language_code: Our internal language code (e.g., "lt", "zh")
    - gender: "m" for male, "f" for female
    - model_name: Piper model identifier (e.g., "human-high", "lessac-high")

    Voice naming convention for UI: piper-{lang}-{gender}{variant}
    Examples: piper-lt-m1, piper-lt-f1, piper-zh-m1

    Gender notation:
    - m1, m2 = male voices 1 and 2
    - f1, f2 = female voices 1 and 2

    Note: Uses highest quality models available for each voice.
    """

    # Lithuanian voices
    # Using simplified naming: piper-lt-m1, piper-lt-f1, etc.
    PIPER_LT_M1 = ("lt", "m", "human-medium")  # Male voice

    # Chinese (Mandarin) voices
    PIPER_ZH_M1 = ("zh", "m", "huayan-medium")  # Male voice
    PIPER_ZH_F1 = ("zh", "f", "huayan-x_low")   # Female voice

    # Korean voices
    PIPER_KO_M1 = ("ko", "m", "human-medium")   # Male voice

    # French voices
    PIPER_FR_M1 = ("fr", "m", "tom-medium")     # Male voice
    PIPER_FR_F1 = ("fr", "f", "siwis-medium")   # Female voice
    PIPER_FR_F2 = ("fr", "f", "upmc-medium")    # Female voice

    # German voices
    PIPER_DE_M1 = ("de", "m", "thorsten-high")  # Male voice (high quality)
    PIPER_DE_F1 = ("de", "f", "eva_k-x_low")    # Female voice
    PIPER_DE_F2 = ("de", "f", "karlsson-low")   # Female voice

    # Spanish voices
    PIPER_ES_M1 = ("es", "m", "carlfm-x_low")   # Male voice
    PIPER_ES_M2 = ("es", "m", "davefx-medium")  # Male voice

    # Portuguese voices
    PIPER_PT_M1 = ("pt", "m", "tugao-medium")   # Male voice

    # Vietnamese voices
    PIPER_VI_M1 = ("vi", "m", "vais1000-medium")  # Male voice
    PIPER_VI_F1 = ("vi", "f", "25hours-single-low")  # Female voice

    # Swahili voices
    # Note: Piper does not have Swahili voices available yet

    @property
    def language_code(self) -> str:
        """Get the language code for this voice."""
        return self.value[0]

    @property
    def gender(self) -> str:
        """Get the gender for this voice ('m' or 'f')."""
        return self.value[1]

    @property
    def model_name(self) -> str:
        """Get the Piper model name for this voice."""
        return self.value[2]

    @property
    def piper_identifier(self) -> str:
        """
        Get the Piper voice identifier.

        Format: {language_region}-{model_name}
        Example: lt_LT-human-medium, fr_FR-siwis-medium

        This identifier is used to locate the voice model file.
        """
        piper_lang = PIPER_LANGUAGE_CODES.get(self.language_code, self.language_code)
        return f"{piper_lang}-{self.model_name}"

    @property
    def ui_name(self) -> str:
        """
        Get the simplified UI display name.

        Returns the enum name in lowercase, replacing underscores with hyphens.
        Example: PIPER_LT_M1 -> piper-lt-m1
        """
        return self.name.lower().replace("_", "-")

    @classmethod
    def get_voices_for_language(cls, language_code: str):
        """Get all available voices for a specific language."""
        return [voice for voice in cls if voice.language_code == language_code]

    @classmethod
    def get_default_voices_for_language(cls, language_code: str):
        """Get default voices for a language."""
        return cls.get_voices_for_language(language_code)

    @classmethod
    def from_ui_name(cls, ui_name: str):
        """
        Get a PiperVoice from its UI name.

        Args:
            ui_name: UI name like "piper-lt-m1"

        Returns:
            PiperVoice enum value or None if not found
        """
        enum_name = ui_name.upper().replace("-", "_")
        try:
            return cls[enum_name]
        except KeyError:
            return None


# Default voices for each language
DEFAULT_PIPER_VOICES = {
    "lt": [PiperVoice.PIPER_LT_M1],
    "zh": [PiperVoice.PIPER_ZH_M1, PiperVoice.PIPER_ZH_F1],
    "ko": [PiperVoice.PIPER_KO_M1],
    "fr": [PiperVoice.PIPER_FR_M1, PiperVoice.PIPER_FR_F1, PiperVoice.PIPER_FR_F2],
    "de": [PiperVoice.PIPER_DE_M1, PiperVoice.PIPER_DE_F1, PiperVoice.PIPER_DE_F2],
    "es": [PiperVoice.PIPER_ES_M1, PiperVoice.PIPER_ES_M2],
    "pt": [PiperVoice.PIPER_PT_M1],
    "vi": [PiperVoice.PIPER_VI_M1, PiperVoice.PIPER_VI_F1],
    "sw": [],  # No Piper voices available yet
}

# Recommended voices (same as default - using highest quality available)
RECOMMENDED_VOICES = {
    "lt": [PiperVoice.PIPER_LT_M1],
    "zh": [PiperVoice.PIPER_ZH_M1, PiperVoice.PIPER_ZH_F1],
    "ko": [PiperVoice.PIPER_KO_M1],
    "fr": [PiperVoice.PIPER_FR_M1, PiperVoice.PIPER_FR_F1, PiperVoice.PIPER_FR_F2],
    "de": [PiperVoice.PIPER_DE_M1, PiperVoice.PIPER_DE_F1, PiperVoice.PIPER_DE_F2],
    "es": [PiperVoice.PIPER_ES_M1, PiperVoice.PIPER_ES_M2],
    "pt": [PiperVoice.PIPER_PT_M1],
    "vi": [PiperVoice.PIPER_VI_M1, PiperVoice.PIPER_VI_F1],
    "sw": [],
}
