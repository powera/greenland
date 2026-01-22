#!/usr/bin/python3
"""Type definitions for Qwen3-TTS audio generation."""

from enum import Enum
from typing import Optional

# Mapping of our language codes to Qwen3-TTS language names
QWEN_LANGUAGE_NAMES = {
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "it": "Italian",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
}

# Voice design prompts for different voice types
# These prompts are used with the VoiceDesign model to create distinct voices
VOICE_DESIGN_PROMPTS = {
    # Female voices
    "f1_soprano": (
        "A young woman with a bright, clear soprano voice. Her pitch is high and light, "
        "with a cheerful and energetic tone. She speaks with crisp articulation and "
        "a warm, friendly manner."
    ),
    "f2_alto": (
        "A mature woman with a rich, warm alto voice. Her pitch is lower and more resonant, "
        "with a calm and confident tone. She speaks with smooth, measured delivery and "
        "a soothing, professional manner."
    ),
    # Male voices
    "m1_tenor": (
        "A young man with a clear, bright tenor voice. His pitch is in the higher male range, "
        "with an energetic and engaging tone. He speaks with precise articulation and "
        "a friendly, approachable manner."
    ),
    "m2_bass": (
        "A mature man with a deep, resonant bass voice. His pitch is low and powerful, "
        "with a calm and authoritative tone. He speaks with deliberate pacing and "
        "a commanding, trustworthy manner."
    ),
}

# Language-specific voice customizations for more natural speech
LANGUAGE_VOICE_HINTS = {
    "zh": {
        "f1": "speaks standard Mandarin with clear tones",
        "f2": "speaks standard Mandarin with measured, elegant tones",
        "m1": "speaks standard Mandarin with clear, precise tones",
        "m2": "speaks standard Mandarin with deep, authoritative tones",
    },
    "ja": {
        "f1": "speaks polite Japanese with bright, feminine intonation",
        "f2": "speaks polite Japanese with calm, mature intonation",
        "m1": "speaks polite Japanese with clear, energetic delivery",
        "m2": "speaks polite Japanese with deep, respectful delivery",
    },
    "ko": {
        "f1": "speaks standard Korean with bright, youthful intonation",
        "f2": "speaks standard Korean with warm, mature intonation",
        "m1": "speaks standard Korean with clear, friendly delivery",
        "m2": "speaks standard Korean with deep, respectful delivery",
    },
    "fr": {
        "f1": "speaks French with bright Parisian intonation",
        "f2": "speaks French with elegant, measured Parisian delivery",
        "m1": "speaks French with clear, engaging Parisian intonation",
        "m2": "speaks French with deep, sophisticated Parisian delivery",
    },
    "it": {
        "f1": "speaks Italian with bright, melodic intonation",
        "f2": "speaks Italian with warm, expressive delivery",
        "m1": "speaks Italian with clear, animated intonation",
        "m2": "speaks Italian with deep, resonant delivery",
    },
    "de": {
        "f1": "speaks German with clear, precise High German pronunciation",
        "f2": "speaks German with warm, measured High German delivery",
        "m1": "speaks German with clear, energetic High German pronunciation",
        "m2": "speaks German with deep, authoritative High German delivery",
    },
    "es": {
        "f1": "speaks Castilian Spanish with bright, clear pronunciation",
        "f2": "speaks Castilian Spanish with warm, elegant delivery",
        "m1": "speaks Castilian Spanish with clear, engaging pronunciation",
        "m2": "speaks Castilian Spanish with deep, commanding delivery",
    },
    "pt": {
        "f1": "speaks European Portuguese with bright, clear pronunciation",
        "f2": "speaks European Portuguese with warm, measured delivery",
        "m1": "speaks European Portuguese with clear, energetic pronunciation",
        "m2": "speaks European Portuguese with deep, authoritative delivery",
    },
}


class QwenVoice(Enum):
    """
    Available Qwen3-TTS voices with gender and pitch-based naming.

    Each voice has a simplified name for UI display. The value tuple contains:
    - language_code: Our internal language code (e.g., "zh", "ja", "ko")
    - gender: "m" for male, "f" for female
    - pitch_type: Voice pitch category ("soprano", "alto", "tenor", "bass")
    - model_variant: Qwen model variant ("voice_design", "custom_voice", "base")

    Voice naming convention for UI: qwen-{lang}-{gender}{variant}
    Examples: qwen-zh-f1, qwen-ja-m2, qwen-fr-f2

    Gender/pitch notation:
    - f1 = female soprano (higher pitch)
    - f2 = female alto (lower pitch)
    - m1 = male tenor (higher pitch)
    - m2 = male bass (lower pitch)

    Note: Uses VoiceDesign model by default for maximum flexibility.
    """

    # Chinese (Mandarin) voices
    QWEN_ZH_F1 = ("zh", "f", "soprano", "voice_design")
    QWEN_ZH_F2 = ("zh", "f", "alto", "voice_design")
    QWEN_ZH_M1 = ("zh", "m", "tenor", "voice_design")
    QWEN_ZH_M2 = ("zh", "m", "bass", "voice_design")

    # Japanese voices
    QWEN_JA_F1 = ("ja", "f", "soprano", "voice_design")
    QWEN_JA_F2 = ("ja", "f", "alto", "voice_design")
    QWEN_JA_M1 = ("ja", "m", "tenor", "voice_design")
    QWEN_JA_M2 = ("ja", "m", "bass", "voice_design")

    # Korean voices
    QWEN_KO_F1 = ("ko", "f", "soprano", "voice_design")
    QWEN_KO_F2 = ("ko", "f", "alto", "voice_design")
    QWEN_KO_M1 = ("ko", "m", "tenor", "voice_design")
    QWEN_KO_M2 = ("ko", "m", "bass", "voice_design")

    # French voices
    QWEN_FR_F1 = ("fr", "f", "soprano", "voice_design")
    QWEN_FR_F2 = ("fr", "f", "alto", "voice_design")
    QWEN_FR_M1 = ("fr", "m", "tenor", "voice_design")
    QWEN_FR_M2 = ("fr", "m", "bass", "voice_design")

    # Italian voices
    QWEN_IT_F1 = ("it", "f", "soprano", "voice_design")
    QWEN_IT_F2 = ("it", "f", "alto", "voice_design")
    QWEN_IT_M1 = ("it", "m", "tenor", "voice_design")
    QWEN_IT_M2 = ("it", "m", "bass", "voice_design")

    # German voices
    QWEN_DE_F1 = ("de", "f", "soprano", "voice_design")
    QWEN_DE_F2 = ("de", "f", "alto", "voice_design")
    QWEN_DE_M1 = ("de", "m", "tenor", "voice_design")
    QWEN_DE_M2 = ("de", "m", "bass", "voice_design")

    # Spanish voices
    QWEN_ES_F1 = ("es", "f", "soprano", "voice_design")
    QWEN_ES_F2 = ("es", "f", "alto", "voice_design")
    QWEN_ES_M1 = ("es", "m", "tenor", "voice_design")
    QWEN_ES_M2 = ("es", "m", "bass", "voice_design")

    # Portuguese voices
    QWEN_PT_F1 = ("pt", "f", "soprano", "voice_design")
    QWEN_PT_F2 = ("pt", "f", "alto", "voice_design")
    QWEN_PT_M1 = ("pt", "m", "tenor", "voice_design")
    QWEN_PT_M2 = ("pt", "m", "bass", "voice_design")

    @property
    def language_code(self) -> str:
        """Get the language code for this voice."""
        return self.value[0]

    @property
    def gender(self) -> str:
        """Get the gender for this voice ('m' or 'f')."""
        return self.value[1]

    @property
    def pitch_type(self) -> str:
        """Get the pitch type for this voice (soprano, alto, tenor, bass)."""
        return self.value[2]

    @property
    def model_variant(self) -> str:
        """Get the model variant for this voice."""
        return self.value[3]

    @property
    def qwen_language(self) -> str:
        """
        Get the Qwen language name for this voice.

        Returns the language name in Qwen's expected format.
        """
        return QWEN_LANGUAGE_NAMES.get(self.language_code, self.language_code)

    @property
    def voice_design_prompt(self) -> str:
        """
        Get the voice design prompt for this voice.

        Returns a detailed prompt describing the voice characteristics
        for use with the VoiceDesign model.
        """
        # Get base prompt for pitch type
        if self.gender == "f":
            if self.pitch_type == "soprano":
                base_prompt = VOICE_DESIGN_PROMPTS["f1_soprano"]
            else:  # alto
                base_prompt = VOICE_DESIGN_PROMPTS["f2_alto"]
        else:  # male
            if self.pitch_type == "tenor":
                base_prompt = VOICE_DESIGN_PROMPTS["m1_tenor"]
            else:  # bass
                base_prompt = VOICE_DESIGN_PROMPTS["m2_bass"]

        # Get language-specific hint
        voice_key = f"{self.gender}{'1' if self.pitch_type in ('soprano', 'tenor') else '2'}"
        lang_hints = LANGUAGE_VOICE_HINTS.get(self.language_code, {})
        lang_hint = lang_hints.get(voice_key, "")

        if lang_hint:
            return (
                f"{base_prompt} She {lang_hint}."
                if self.gender == "f"
                else f"{base_prompt} He {lang_hint}."
            )
        return base_prompt

    @property
    def ui_name(self) -> str:
        """
        Get the simplified UI display name.

        Returns the enum name in lowercase, replacing underscores with hyphens.
        Example: QWEN_ZH_F1 -> qwen-zh-f1
        """
        return self.name.lower().replace("_", "-")

    @classmethod
    def get_voices_for_language(cls, language_code: str) -> list["QwenVoice"]:
        """Get all available voices for a specific language."""
        return [voice for voice in cls if voice.language_code == language_code]

    @classmethod
    def get_default_voices_for_language(cls, language_code: str) -> list["QwenVoice"]:
        """Get default voices for a language (all 4 voices)."""
        return cls.get_voices_for_language(language_code)

    @classmethod
    def from_ui_name(cls, ui_name: str) -> Optional["QwenVoice"]:
        """
        Get a QwenVoice from its UI name.

        Args:
            ui_name: UI name like "qwen-zh-f1"

        Returns:
            QwenVoice enum value or None if not found
        """
        enum_name = ui_name.upper().replace("-", "_")
        try:
            return cls[enum_name]
        except KeyError:
            return None


# Default voices for each language (all 4 voices per language)
DEFAULT_QWEN_VOICES = {
    "zh": [QwenVoice.QWEN_ZH_F1, QwenVoice.QWEN_ZH_F2, QwenVoice.QWEN_ZH_M1, QwenVoice.QWEN_ZH_M2],
    "ja": [QwenVoice.QWEN_JA_F1, QwenVoice.QWEN_JA_F2, QwenVoice.QWEN_JA_M1, QwenVoice.QWEN_JA_M2],
    "ko": [QwenVoice.QWEN_KO_F1, QwenVoice.QWEN_KO_F2, QwenVoice.QWEN_KO_M1, QwenVoice.QWEN_KO_M2],
    "fr": [QwenVoice.QWEN_FR_F1, QwenVoice.QWEN_FR_F2, QwenVoice.QWEN_FR_M1, QwenVoice.QWEN_FR_M2],
    "it": [QwenVoice.QWEN_IT_F1, QwenVoice.QWEN_IT_F2, QwenVoice.QWEN_IT_M1, QwenVoice.QWEN_IT_M2],
    "de": [QwenVoice.QWEN_DE_F1, QwenVoice.QWEN_DE_F2, QwenVoice.QWEN_DE_M1, QwenVoice.QWEN_DE_M2],
    "es": [QwenVoice.QWEN_ES_F1, QwenVoice.QWEN_ES_F2, QwenVoice.QWEN_ES_M1, QwenVoice.QWEN_ES_M2],
    "pt": [QwenVoice.QWEN_PT_F1, QwenVoice.QWEN_PT_F2, QwenVoice.QWEN_PT_M1, QwenVoice.QWEN_PT_M2],
}

# Recommended voices (one male, one female per language for typical use)
RECOMMENDED_VOICES = {
    "zh": [QwenVoice.QWEN_ZH_F2, QwenVoice.QWEN_ZH_M1],  # Alto + Tenor (balanced)
    "ja": [QwenVoice.QWEN_JA_F2, QwenVoice.QWEN_JA_M1],
    "ko": [QwenVoice.QWEN_KO_F2, QwenVoice.QWEN_KO_M1],
    "fr": [QwenVoice.QWEN_FR_F2, QwenVoice.QWEN_FR_M1],
    "it": [QwenVoice.QWEN_IT_F2, QwenVoice.QWEN_IT_M1],
    "de": [QwenVoice.QWEN_DE_F2, QwenVoice.QWEN_DE_M1],
    "es": [QwenVoice.QWEN_ES_F2, QwenVoice.QWEN_ES_M1],
    "pt": [QwenVoice.QWEN_PT_F2, QwenVoice.QWEN_PT_M1],
}

# Supported languages list
SUPPORTED_LANGUAGES = list(QWEN_LANGUAGE_NAMES.keys())
