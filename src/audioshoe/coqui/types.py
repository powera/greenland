#!/usr/bin/python3
"""Type definitions for Coqui TTS audio generation."""

from enum import Enum
from typing import Optional

# Mapping of our language codes to Coqui language codes
COQUI_LANGUAGE_CODES = {
    "zh": "zh-cn",    # Chinese (Mandarin)
    "ko": "ko",       # Korean
    "lt": "lt",       # Lithuanian
    "vi": "vi",       # Vietnamese
    "sw": "sw",       # Swahili
    "fr": "fr",       # French
    "de": "de",       # German
    "es": "es",       # Spanish
    "pt": "pt",       # Portuguese
}


class CoquiVoice(Enum):
    """
    Available Coqui TTS voices with gender-based naming.

    Each voice has a simplified name for UI display. The value tuple contains:
    - language_code: Our internal language code (e.g., "lt", "zh")
    - gender: "m" for male, "f" for female
    - model_name: Coqui model identifier (e.g., "tts_models/multilingual/multi-dataset/xtts_v2")
    - speaker_name: Optional speaker name/ID for multi-speaker models

    Voice naming convention for UI: coqui-{lang}-{gender}{variant}
    Examples: coqui-lt-m1, coqui-zh-f1, coqui-fr-m1

    Gender notation:
    - m1, m2 = male voices 1 and 2
    - f1, f2 = female voices 1 and 2

    Note: Uses highest quality models available for each voice.
    """

    # Lithuanian voices
    # Using XTTS v2 multilingual model
    COQUI_LT_M1 = ("lt", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_LT_F1 = ("lt", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # Chinese (Mandarin) voices
    COQUI_ZH_M1 = ("zh", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_ZH_F1 = ("zh", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # Korean voices
    COQUI_KO_M1 = ("ko", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_KO_F1 = ("ko", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # French voices
    COQUI_FR_M1 = ("fr", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_FR_F1 = ("fr", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # German voices
    COQUI_DE_M1 = ("de", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_DE_F1 = ("de", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # Spanish voices
    COQUI_ES_M1 = ("es", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_ES_F1 = ("es", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # Portuguese voices
    COQUI_PT_M1 = ("pt", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_PT_F1 = ("pt", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # Vietnamese voices
    COQUI_VI_M1 = ("vi", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_VI_F1 = ("vi", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

    # Swahili voices
    COQUI_SW_M1 = ("sw", "m", "tts_models/multilingual/multi-dataset/xtts_v2", None)
    COQUI_SW_F1 = ("sw", "f", "tts_models/multilingual/multi-dataset/xtts_v2", None)

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
        """Get the Coqui model name for this voice."""
        return self.value[2]

    @property
    def speaker_name(self) -> Optional[str]:
        """Get the speaker name/ID for this voice (if applicable)."""
        return self.value[3]

    @property
    def coqui_language(self) -> str:
        """
        Get the Coqui language code for this voice.

        Returns the language code in Coqui's expected format.
        """
        return COQUI_LANGUAGE_CODES.get(self.language_code, self.language_code)

    @property
    def ui_name(self) -> str:
        """
        Get the simplified UI display name.

        Returns the enum name in lowercase, replacing underscores with hyphens.
        Example: COQUI_LT_M1 -> coqui-lt-m1
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
        Get a CoquiVoice from its UI name.

        Args:
            ui_name: UI name like "coqui-lt-m1"

        Returns:
            CoquiVoice enum value or None if not found
        """
        enum_name = ui_name.upper().replace("-", "_")
        try:
            return cls[enum_name]
        except KeyError:
            return None


# Default voices for each language
DEFAULT_COQUI_VOICES = {
    "lt": [CoquiVoice.COQUI_LT_M1, CoquiVoice.COQUI_LT_F1],
    "zh": [CoquiVoice.COQUI_ZH_M1, CoquiVoice.COQUI_ZH_F1],
    "ko": [CoquiVoice.COQUI_KO_M1, CoquiVoice.COQUI_KO_F1],
    "fr": [CoquiVoice.COQUI_FR_M1, CoquiVoice.COQUI_FR_F1],
    "de": [CoquiVoice.COQUI_DE_M1, CoquiVoice.COQUI_DE_F1],
    "es": [CoquiVoice.COQUI_ES_M1, CoquiVoice.COQUI_ES_F1],
    "pt": [CoquiVoice.COQUI_PT_M1, CoquiVoice.COQUI_PT_F1],
    "vi": [CoquiVoice.COQUI_VI_M1, CoquiVoice.COQUI_VI_F1],
    "sw": [CoquiVoice.COQUI_SW_M1, CoquiVoice.COQUI_SW_F1],
}

# Recommended voices (same as default - using XTTS v2 for all)
RECOMMENDED_VOICES = {
    "lt": [CoquiVoice.COQUI_LT_M1, CoquiVoice.COQUI_LT_F1],
    "zh": [CoquiVoice.COQUI_ZH_M1, CoquiVoice.COQUI_ZH_F1],
    "ko": [CoquiVoice.COQUI_KO_M1, CoquiVoice.COQUI_KO_F1],
    "fr": [CoquiVoice.COQUI_FR_M1, CoquiVoice.COQUI_FR_F1],
    "de": [CoquiVoice.COQUI_DE_M1, CoquiVoice.COQUI_DE_F1],
    "es": [CoquiVoice.COQUI_ES_M1, CoquiVoice.COQUI_ES_F1],
    "pt": [CoquiVoice.COQUI_PT_M1, CoquiVoice.COQUI_PT_F1],
    "vi": [CoquiVoice.COQUI_VI_M1, CoquiVoice.COQUI_VI_F1],
    "sw": [CoquiVoice.COQUI_SW_M1, CoquiVoice.COQUI_SW_F1],
}
