#!/usr/bin/python3
"""GPT voice definitions for OpenAI TTS audio generation.

This module defines the mapping between OpenAI TTS voices and our internal
voice naming convention, including gender and per-language character names.

Voice naming convention for UI: gpt-{lang}-{gender}{variant}
Examples: gpt-lt-f1, gpt-zh-m1, gpt-fr-f2

Gender/variant notation:
- f1 = primary female voice
- f2 = secondary female voice (if available)
- m1 = primary male voice
- m2 = secondary male voice (if available)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from .types import Voice


@dataclass
class GptVoiceInfo:
    """Information about an OpenAI TTS voice."""

    openai_voice: Voice  # The underlying OpenAI voice enum
    gender: str  # "m" or "f"
    variant: int  # 1 or 2 (primary or secondary)
    description: str  # Voice description


# OpenAI voice metadata
# Based on listening tests and community observations
OPENAI_VOICE_INFO: Dict[Voice, GptVoiceInfo] = {
    Voice.ALLOY: GptVoiceInfo(
        openai_voice=Voice.ALLOY,
        gender="f",
        variant=2,
        description="Female, deeper/warmer tone",
    ),
    Voice.ASH: GptVoiceInfo(
        openai_voice=Voice.ASH,
        gender="m",
        variant=1,
        description="Male, deep voice",
    ),
    Voice.NOVA: GptVoiceInfo(
        openai_voice=Voice.NOVA,
        gender="f",
        variant=1,
        description="Female, clear/bright tone",
    ),
    Voice.ECHO: GptVoiceInfo(
        openai_voice=Voice.ECHO,
        gender="m",
        variant=2,
        description="Male, mid-range voice",
    ),
    Voice.ONYX: GptVoiceInfo(
        openai_voice=Voice.ONYX,
        gender="m",
        variant=3,
        description="Male, deep/resonant voice",
    ),
    Voice.SHIMMER: GptVoiceInfo(
        openai_voice=Voice.SHIMMER,
        gender="f",
        variant=3,
        description="Female, light/airy tone",
    ),
    Voice.FABLE: GptVoiceInfo(
        openai_voice=Voice.FABLE,
        gender="m",
        variant=4,
        description="Male, expressive/storytelling voice",
    ),
    Voice.CORAL: GptVoiceInfo(
        openai_voice=Voice.CORAL,
        gender="f",
        variant=4,
        description="Female voice",
    ),
    Voice.SAGE: GptVoiceInfo(
        openai_voice=Voice.SAGE,
        gender="f",
        variant=5,
        description="Female voice",
    ),
    Voice.BALLAD: GptVoiceInfo(
        openai_voice=Voice.BALLAD,
        gender="m",
        variant=5,
        description="Male, melodic voice",
    ),
}


# Default voice assignments per gender
# These are the recommended voices to use
DEFAULT_FEMALE_VOICE = Voice.NOVA  # Primary female
DEFAULT_MALE_VOICE = Voice.ASH  # Primary male
SECONDARY_FEMALE_VOICE = Voice.ALLOY  # Secondary female (deeper)
SECONDARY_MALE_VOICE = Voice.ECHO  # Secondary male


class GptVoice(Enum):
    """
    GPT voice definitions with language and gender.

    Each voice maps to an OpenAI TTS voice with metadata for:
    - Language code
    - Gender (m/f)
    - Variant (1 = primary, 2 = secondary)
    - OpenAI voice to use

    Voice naming: GPT_{LANG}_{GENDER}{VARIANT}
    UI name: gpt-{lang}-{gender}{variant}
    """

    # Lithuanian voices
    GPT_LT_F1 = ("lt", "f", 1, Voice.NOVA)
    GPT_LT_F2 = ("lt", "f", 2, Voice.ALLOY)
    GPT_LT_M1 = ("lt", "m", 1, Voice.ASH)
    GPT_LT_M2 = ("lt", "m", 2, Voice.ECHO)

    # Chinese (Mandarin) voices
    GPT_ZH_F1 = ("zh", "f", 1, Voice.NOVA)
    GPT_ZH_F2 = ("zh", "f", 2, Voice.ALLOY)
    GPT_ZH_M1 = ("zh", "m", 1, Voice.ASH)
    GPT_ZH_M2 = ("zh", "m", 2, Voice.ECHO)

    # Spanish voices
    GPT_ES_F1 = ("es", "f", 1, Voice.NOVA)
    GPT_ES_F2 = ("es", "f", 2, Voice.ALLOY)
    GPT_ES_M1 = ("es", "m", 1, Voice.ASH)
    GPT_ES_M2 = ("es", "m", 2, Voice.ECHO)

    # French voices
    GPT_FR_F1 = ("fr", "f", 1, Voice.NOVA)
    GPT_FR_F2 = ("fr", "f", 2, Voice.ALLOY)
    GPT_FR_M1 = ("fr", "m", 1, Voice.ASH)
    GPT_FR_M2 = ("fr", "m", 2, Voice.ECHO)

    # Italian voices
    GPT_IT_F1 = ("it", "f", 1, Voice.NOVA)
    GPT_IT_F2 = ("it", "f", 2, Voice.ALLOY)
    GPT_IT_M1 = ("it", "m", 1, Voice.ASH)
    GPT_IT_M2 = ("it", "m", 2, Voice.ECHO)

    # Portuguese voices
    GPT_PT_F1 = ("pt", "f", 1, Voice.NOVA)
    GPT_PT_F2 = ("pt", "f", 2, Voice.ALLOY)
    GPT_PT_M1 = ("pt", "m", 1, Voice.ASH)
    GPT_PT_M2 = ("pt", "m", 2, Voice.ECHO)

    # Dutch voices
    GPT_NL_F1 = ("nl", "f", 1, Voice.NOVA)
    GPT_NL_F2 = ("nl", "f", 2, Voice.ALLOY)
    GPT_NL_M1 = ("nl", "m", 1, Voice.ASH)
    GPT_NL_M2 = ("nl", "m", 2, Voice.ECHO)

    # German voices
    GPT_DE_F1 = ("de", "f", 1, Voice.NOVA)
    GPT_DE_F2 = ("de", "f", 2, Voice.ALLOY)
    GPT_DE_M1 = ("de", "m", 1, Voice.ASH)
    GPT_DE_M2 = ("de", "m", 2, Voice.ECHO)

    # Swedish voices
    GPT_SV_F1 = ("sv", "f", 1, Voice.NOVA)
    GPT_SV_F2 = ("sv", "f", 2, Voice.ALLOY)
    GPT_SV_M1 = ("sv", "m", 1, Voice.ASH)
    GPT_SV_M2 = ("sv", "m", 2, Voice.ECHO)

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
        """Get the variant number (1 = primary, 2 = secondary)."""
        return self.value[2]

    @property
    def openai_voice(self) -> Voice:
        """Get the underlying OpenAI Voice enum."""
        return self.value[3]

    @property
    def ui_name(self) -> str:
        """
        Get the UI display name.

        Returns name like 'gpt-lt-f1' for use in URLs and display.
        """
        return f"gpt-{self.language_code}-{self.gender}{self.variant}"

    @property
    def path_name(self) -> str:
        """
        Get the path-safe name for S3 URLs.

        Returns lowercase character name (e.g., 'ruta', 'jonas', 'meiling').
        Falls back to ui_name if character name not defined.
        """
        voice_key = f"{self.gender}{self.variant}"
        lang_names = CHARACTER_NAMES.get(self.language_code, {})
        name = lang_names.get(voice_key)
        if name:
            # Normalize: lowercase, remove accents for path safety
            import unicodedata

            # Normalize to decomposed form, remove combining marks, lowercase
            normalized = unicodedata.normalize("NFD", name)
            ascii_name = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
            return ascii_name.lower()
        return self.ui_name

    @property
    def openai_voice_name(self) -> str:
        """Get the OpenAI voice name (e.g., 'nova', 'ash')."""
        return self.openai_voice.value

    @classmethod
    def get_voices_for_language(cls, language_code: str) -> List["GptVoice"]:
        """Get all available voices for a specific language."""
        return [voice for voice in cls if voice.language_code == language_code]

    @classmethod
    def get_default_voices_for_language(cls, language_code: str) -> List["GptVoice"]:
        """Get default voices for a language (primary male and female)."""
        return [
            voice for voice in cls if voice.language_code == language_code and voice.variant == 1
        ]

    @classmethod
    def from_ui_name(cls, ui_name: str) -> Optional["GptVoice"]:
        """
        Get a GptVoice from its UI name.

        Args:
            ui_name: UI name like 'gpt-lt-f1'

        Returns:
            GptVoice enum value or None if not found
        """
        # Convert 'gpt-lt-f1' to 'GPT_LT_F1'
        enum_name = ui_name.upper().replace("-", "_")
        try:
            return cls[enum_name]
        except KeyError:
            return None

    @classmethod
    def from_openai_voice(cls, openai_voice: Voice, language_code: str) -> Optional["GptVoice"]:
        """
        Get a GptVoice from an OpenAI voice and language.

        Args:
            openai_voice: OpenAI Voice enum
            language_code: Language code

        Returns:
            First matching GptVoice or None
        """
        for voice in cls:
            if voice.openai_voice == openai_voice and voice.language_code == language_code:
                return voice
        return None


# Default voices per language (primary male and female)
DEFAULT_GPT_VOICES: Dict[str, List[GptVoice]] = {
    "lt": [GptVoice.GPT_LT_F1, GptVoice.GPT_LT_M1],
    "zh": [GptVoice.GPT_ZH_F1, GptVoice.GPT_ZH_M1],
    "es": [GptVoice.GPT_ES_F1, GptVoice.GPT_ES_M1],
    "fr": [GptVoice.GPT_FR_F1, GptVoice.GPT_FR_M1],
    "it": [GptVoice.GPT_IT_F1, GptVoice.GPT_IT_M1],
    "pt": [GptVoice.GPT_PT_F1, GptVoice.GPT_PT_M1],
    "nl": [GptVoice.GPT_NL_F1, GptVoice.GPT_NL_M1],
    "de": [GptVoice.GPT_DE_F1, GptVoice.GPT_DE_M1],
    "sv": [GptVoice.GPT_SV_F1, GptVoice.GPT_SV_M1],
}

# All voices per language (all 4 variants)
ALL_GPT_VOICES: Dict[str, List[GptVoice]] = {
    lang: GptVoice.get_voices_for_language(lang)
    for lang in ["lt", "zh", "es", "fr", "it", "pt", "nl", "de", "sv"]
}

# Supported languages
SUPPORTED_LANGUAGES = list(DEFAULT_GPT_VOICES.keys())


# Character names per language (for future use in UI)
# These can be customized per language for a more personalized experience
# Format: {language_code: {voice_ui_suffix: character_name}}
# e.g., {"lt": {"f1": "Rūta", "m1": "Jonas"}}
CHARACTER_NAMES: Dict[str, Dict[str, str]] = {
    # Lithuanian
    "lt": {
        "f1": "Rūta",  # Female, primary (Nova)
        "f2": "Eglė",  # Female, secondary (Alloy)
        "m1": "Jonas",  # Male, primary (Ash)
        "m2": "Tomas",  # Male, secondary (Echo)
    },
    # Chinese (romanized names for UI, Chinese characters for display)
    "zh": {
        "f1": "Meiling",  # 美玲 - Female, primary (Nova)
        "f2": "Yating",  # 雅婷 - Female, secondary (Alloy)
        "m1": "Zhiyuan",  # 志远 - Male, primary (Ash)
        "m2": "Haoran",  # 浩然 - Male, secondary (Echo)
    },
    # Spanish
    "es": {
        "f1": "María",  # Female, primary (Nova)
        "f2": "Carmen",  # Female, secondary (Alloy)
        "m1": "Carlos",  # Male, primary (Ash)
        "m2": "Miguel",  # Male, secondary (Echo)
    },
    # French
    "fr": {
        "f1": "Marie",  # Female, primary (Nova)
        "f2": "Sophie",  # Female, secondary (Alloy)
        "m1": "Pierre",  # Male, primary (Ash)
        "m2": "Jean",  # Male, secondary (Echo)
    },
    # Italian
    "it": {
        "f1": "Giulia",  # Female, primary (Nova)
        "f2": "Chiara",  # Female, secondary (Alloy)
        "m1": "Luca",  # Male, primary (Ash)
        "m2": "Marco",  # Male, secondary (Echo)
    },
    # Portuguese
    "pt": {
        "f1": "Ana",  # Female, primary (Nova)
        "f2": "Beatriz",  # Female, secondary (Alloy)
        "m1": "Joao",  # Male, primary (Ash)
        "m2": "Tiago",  # Male, secondary (Echo)
    },
    # Dutch
    "nl": {
        "f1": "Sanne",  # Female, primary (Nova)
        "f2": "Lotte",  # Female, secondary (Alloy)
        "m1": "Daan",  # Male, primary (Ash)
        "m2": "Joris",  # Male, secondary (Echo)
    },
    # German
    "de": {
        "f1": "Anna",  # Female, primary (Nova)
        "f2": "Lea",  # Female, secondary (Alloy)
        "m1": "Lukas",  # Male, primary (Ash)
        "m2": "Felix",  # Male, secondary (Echo)
    },
    # Swedish
    "sv": {
        "f1": "Elsa",  # Female, primary (Nova)
        "f2": "Alva",  # Female, secondary (Alloy)
        "m1": "Erik",  # Male, primary (Ash)
        "m2": "Oskar",  # Male, secondary (Echo)
    },
}

# Language display names for character descriptions
LANGUAGE_DISPLAY_NAMES: Dict[str, str] = {
    "lt": "Lithuanian",
    "zh": "Chinese",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "de": "German",
    "sv": "Swedish",
}


def get_character_description(voice: GptVoice) -> Optional[str]:
    """
    Get the character description/flavor text for a voice.

    This is prepended to the language-specific pronunciation prompt
    to give the TTS a character persona.

    Variant 1 voices (primary) are language teachers.
    Variant 2 voices (secondary) are ordinary native speakers.

    Args:
        voice: GptVoice enum value

    Returns:
        Character description string or None if not defined
    """
    name = get_character_name(voice)
    if not name:
        return None

    language_name = LANGUAGE_DISPLAY_NAMES.get(voice.language_code)
    if not language_name:
        return None

    if voice.variant == 1:
        return f"You are {name}, a friendly {language_name} language teacher."
    else:
        return f"You are {name}, a native {language_name} speaker."


def get_character_name(voice: GptVoice) -> Optional[str]:
    """
    Get the character name for a voice.

    Args:
        voice: GptVoice enum value

    Returns:
        Character name string or None if not defined
    """
    lang_names = CHARACTER_NAMES.get(voice.language_code, {})
    voice_key = f"{voice.gender}{voice.variant}"
    return lang_names.get(voice_key)
