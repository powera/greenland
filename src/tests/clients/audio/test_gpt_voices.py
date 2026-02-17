#!/usr/bin/env python3
"""
Tests for GPT voice definitions and S3 path generation.

These tests verify:
- GptVoice enum properties work correctly
- Character names and descriptions are properly defined
- S3 path names are ASCII-safe and correctly formatted
"""

import sys
import unittest
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.gpt_voices import (
    ALL_GPT_VOICES,
    CHARACTER_NAMES,
    DEFAULT_GPT_VOICES,
    LANGUAGE_DISPLAY_NAMES,
    SUPPORTED_LANGUAGES,
    GptVoice,
    get_character_description,
    get_character_name,
)
from clients.audio.types import Voice


class TestGptVoiceEnum(unittest.TestCase):
    """Test GptVoice enum properties."""

    def test_language_code_property(self) -> None:
        """Test language_code property returns correct values."""
        self.assertEqual(GptVoice.GPT_LT_F1.language_code, "lt")
        self.assertEqual(GptVoice.GPT_ZH_M1.language_code, "zh")
        self.assertEqual(GptVoice.GPT_ES_F2.language_code, "es")
        self.assertEqual(GptVoice.GPT_FR_M2.language_code, "fr")
        self.assertEqual(GptVoice.GPT_IT_F1.language_code, "it")
        self.assertEqual(GptVoice.GPT_PT_M1.language_code, "pt")
        self.assertEqual(GptVoice.GPT_NL_F2.language_code, "nl")
        self.assertEqual(GptVoice.GPT_DE_M2.language_code, "de")
        self.assertEqual(GptVoice.GPT_SV_F1.language_code, "sv")

    def test_gender_property(self) -> None:
        """Test gender property returns correct values."""
        self.assertEqual(GptVoice.GPT_LT_F1.gender, "f")
        self.assertEqual(GptVoice.GPT_LT_M1.gender, "m")
        self.assertEqual(GptVoice.GPT_ZH_F2.gender, "f")
        self.assertEqual(GptVoice.GPT_ZH_M2.gender, "m")

    def test_variant_property(self) -> None:
        """Test variant property returns correct values."""
        self.assertEqual(GptVoice.GPT_LT_F1.variant, 1)
        self.assertEqual(GptVoice.GPT_LT_F2.variant, 2)
        self.assertEqual(GptVoice.GPT_ZH_M1.variant, 1)
        self.assertEqual(GptVoice.GPT_ZH_M2.variant, 2)

    def test_openai_voice_property(self) -> None:
        """Test openai_voice property returns correct Voice enum."""
        # F1 voices use Nova
        self.assertEqual(GptVoice.GPT_LT_F1.openai_voice, Voice.NOVA)
        self.assertEqual(GptVoice.GPT_ZH_F1.openai_voice, Voice.NOVA)

        # F2 voices use Alloy
        self.assertEqual(GptVoice.GPT_LT_F2.openai_voice, Voice.ALLOY)
        self.assertEqual(GptVoice.GPT_ES_F2.openai_voice, Voice.ALLOY)

        # M1 voices use Ash
        self.assertEqual(GptVoice.GPT_LT_M1.openai_voice, Voice.ASH)
        self.assertEqual(GptVoice.GPT_FR_M1.openai_voice, Voice.ASH)

        # M2 voices use Echo
        self.assertEqual(GptVoice.GPT_LT_M2.openai_voice, Voice.ECHO)
        self.assertEqual(GptVoice.GPT_ZH_M2.openai_voice, Voice.ECHO)

    def test_ui_name_property(self) -> None:
        """Test ui_name property returns correct format."""
        self.assertEqual(GptVoice.GPT_LT_F1.ui_name, "gpt-lt-f1")
        self.assertEqual(GptVoice.GPT_ZH_M2.ui_name, "gpt-zh-m2")
        self.assertEqual(GptVoice.GPT_ES_F2.ui_name, "gpt-es-f2")
        self.assertEqual(GptVoice.GPT_FR_M1.ui_name, "gpt-fr-m1")
        self.assertEqual(GptVoice.GPT_IT_F2.ui_name, "gpt-it-f2")
        self.assertEqual(GptVoice.GPT_SV_M1.ui_name, "gpt-sv-m1")

    def test_openai_voice_name_property(self) -> None:
        """Test openai_voice_name returns the string value."""
        self.assertEqual(GptVoice.GPT_LT_F1.openai_voice_name, "nova")
        self.assertEqual(GptVoice.GPT_LT_M1.openai_voice_name, "ash")
        self.assertEqual(GptVoice.GPT_LT_F2.openai_voice_name, "alloy")
        self.assertEqual(GptVoice.GPT_LT_M2.openai_voice_name, "echo")


class TestGptVoicePathName(unittest.TestCase):
    """Test path_name property for S3 URL generation."""

    def test_path_name_is_lowercase(self) -> None:
        """Test that path_name is always lowercase."""
        for voice in GptVoice:
            self.assertEqual(voice.path_name, voice.path_name.lower())

    def test_path_name_is_ascii(self) -> None:
        """Test that path_name contains only ASCII characters."""
        for voice in GptVoice:
            path_name = voice.path_name
            self.assertTrue(
                path_name.isascii(),
                f"path_name '{path_name}' for {voice.name} contains non-ASCII characters",
            )

    def test_path_name_no_spaces(self) -> None:
        """Test that path_name contains no spaces."""
        for voice in GptVoice:
            self.assertNotIn(" ", voice.path_name)

    def test_path_name_url_safe(self) -> None:
        """Test that path_name is URL-safe (alphanumeric and hyphens only)."""
        import re

        url_safe_pattern = re.compile(r"^[a-z0-9-]+$")
        for voice in GptVoice:
            path_name = voice.path_name
            self.assertTrue(
                url_safe_pattern.match(path_name),
                f"path_name '{path_name}' for {voice.name} is not URL-safe",
            )

    def test_lithuanian_path_names(self) -> None:
        """Test Lithuanian voice path names are correct."""
        self.assertEqual(GptVoice.GPT_LT_F1.path_name, "ruta")
        self.assertEqual(GptVoice.GPT_LT_F2.path_name, "egle")
        self.assertEqual(GptVoice.GPT_LT_M1.path_name, "jonas")
        self.assertEqual(GptVoice.GPT_LT_M2.path_name, "tomas")

    def test_chinese_path_names(self) -> None:
        """Test Chinese voice path names are romanized."""
        self.assertEqual(GptVoice.GPT_ZH_F1.path_name, "meiling")
        self.assertEqual(GptVoice.GPT_ZH_F2.path_name, "yating")
        self.assertEqual(GptVoice.GPT_ZH_M1.path_name, "zhiyuan")
        self.assertEqual(GptVoice.GPT_ZH_M2.path_name, "haoran")

    def test_spanish_path_names(self) -> None:
        """Test Spanish voice path names have accents removed."""
        self.assertEqual(GptVoice.GPT_ES_F1.path_name, "maria")  # María -> maria
        self.assertEqual(GptVoice.GPT_ES_F2.path_name, "carmen")
        self.assertEqual(GptVoice.GPT_ES_M1.path_name, "carlos")
        self.assertEqual(GptVoice.GPT_ES_M2.path_name, "miguel")

    def test_french_path_names(self) -> None:
        """Test French voice path names are correct."""
        self.assertEqual(GptVoice.GPT_FR_F1.path_name, "marie")
        self.assertEqual(GptVoice.GPT_FR_F2.path_name, "sophie")
        self.assertEqual(GptVoice.GPT_FR_M1.path_name, "pierre")
        self.assertEqual(GptVoice.GPT_FR_M2.path_name, "jean")

    def test_secondary_language_path_names(self) -> None:
        """Test secondary language voice path names."""
        self.assertEqual(GptVoice.GPT_IT_F1.path_name, "giulia")
        self.assertEqual(GptVoice.GPT_PT_M1.path_name, "joao")
        self.assertEqual(GptVoice.GPT_NL_M2.path_name, "joris")
        self.assertEqual(GptVoice.GPT_DE_F2.path_name, "lea")
        self.assertEqual(GptVoice.GPT_SV_M2.path_name, "oskar")


class TestGptVoiceLookup(unittest.TestCase):
    """Test GptVoice lookup methods."""

    def test_from_ui_name(self) -> None:
        """Test looking up voice by ui_name."""
        self.assertEqual(GptVoice.from_ui_name("gpt-lt-f1"), GptVoice.GPT_LT_F1)
        self.assertEqual(GptVoice.from_ui_name("gpt-zh-m2"), GptVoice.GPT_ZH_M2)
        self.assertEqual(GptVoice.from_ui_name("GPT-ES-F2"), GptVoice.GPT_ES_F2)

    def test_from_ui_name_invalid(self) -> None:
        """Test looking up invalid ui_name returns None."""
        self.assertIsNone(GptVoice.from_ui_name("invalid"))
        self.assertIsNone(GptVoice.from_ui_name("gpt-xx-f1"))
        self.assertIsNone(GptVoice.from_ui_name(""))

    def test_get_voices_for_language(self) -> None:
        """Test getting all voices for a language."""
        lt_voices = GptVoice.get_voices_for_language("lt")
        self.assertEqual(len(lt_voices), 4)
        self.assertIn(GptVoice.GPT_LT_F1, lt_voices)
        self.assertIn(GptVoice.GPT_LT_F2, lt_voices)
        self.assertIn(GptVoice.GPT_LT_M1, lt_voices)
        self.assertIn(GptVoice.GPT_LT_M2, lt_voices)

    def test_get_default_voices_for_language(self) -> None:
        """Test getting default (primary) voices for a language."""
        lt_defaults = GptVoice.get_default_voices_for_language("lt")
        self.assertEqual(len(lt_defaults), 2)
        self.assertIn(GptVoice.GPT_LT_F1, lt_defaults)
        self.assertIn(GptVoice.GPT_LT_M1, lt_defaults)
        # Secondary voices should not be included
        self.assertNotIn(GptVoice.GPT_LT_F2, lt_defaults)
        self.assertNotIn(GptVoice.GPT_LT_M2, lt_defaults)

    def test_from_openai_voice(self) -> None:
        """Test looking up by OpenAI voice and language."""
        voice = GptVoice.from_openai_voice(Voice.NOVA, "lt")
        self.assertEqual(voice, GptVoice.GPT_LT_F1)

        voice = GptVoice.from_openai_voice(Voice.ASH, "zh")
        self.assertEqual(voice, GptVoice.GPT_ZH_M1)


class TestCharacterNames(unittest.TestCase):
    """Test character name functions."""

    def test_get_character_name(self) -> None:
        """Test getting character name for a voice."""
        self.assertEqual(get_character_name(GptVoice.GPT_LT_F1), "Rūta")
        self.assertEqual(get_character_name(GptVoice.GPT_LT_M1), "Jonas")
        self.assertEqual(get_character_name(GptVoice.GPT_ZH_F1), "Meiling")
        self.assertEqual(get_character_name(GptVoice.GPT_ES_F1), "María")

    def test_all_voices_have_character_names(self) -> None:
        """Test that all voices have character names defined."""
        for voice in GptVoice:
            name = get_character_name(voice)
            self.assertIsNotNone(name, f"Voice {voice.name} has no character name defined")
            self.assertTrue(len(name) > 0)

    def test_get_character_description(self) -> None:
        """Test getting character description for a voice."""
        desc = get_character_description(GptVoice.GPT_LT_F1)
        self.assertIsNotNone(desc)
        self.assertIn("Rūta", desc)
        self.assertIn("Lithuanian", desc)
        self.assertIn("teacher", desc)

        desc = get_character_description(GptVoice.GPT_ZH_M1)
        self.assertIsNotNone(desc)
        self.assertIn("Zhiyuan", desc)
        self.assertIn("Chinese", desc)

    def test_all_voices_have_character_descriptions(self) -> None:
        """Test that all voices have character descriptions defined."""
        for voice in GptVoice:
            desc = get_character_description(voice)
            self.assertIsNotNone(desc, f"Voice {voice.name} has no character description defined")
            self.assertTrue(len(desc) > 0)


class TestSupportedLanguages(unittest.TestCase):
    """Test supported languages configuration."""

    def test_supported_languages(self) -> None:
        """Test that supported languages are correctly defined."""
        self.assertEqual(set(SUPPORTED_LANGUAGES), {"lt", "zh", "es", "fr", "it", "pt", "nl", "de", "sv"})

    def test_default_voices_for_all_languages(self) -> None:
        """Test that default voices are defined for all supported languages."""
        for lang in SUPPORTED_LANGUAGES:
            self.assertIn(lang, DEFAULT_GPT_VOICES)
            self.assertTrue(len(DEFAULT_GPT_VOICES[lang]) > 0)

    def test_all_voices_for_all_languages(self) -> None:
        """Test that all voices are defined for all supported languages."""
        for lang in SUPPORTED_LANGUAGES:
            self.assertIn(lang, ALL_GPT_VOICES)
            self.assertEqual(len(ALL_GPT_VOICES[lang]), 4)

    def test_language_display_names(self) -> None:
        """Test that language display names are defined for all languages."""
        for lang in SUPPORTED_LANGUAGES:
            self.assertIn(lang, LANGUAGE_DISPLAY_NAMES)
            self.assertTrue(len(LANGUAGE_DISPLAY_NAMES[lang]) > 0)


class TestS3PathGeneration(unittest.TestCase):
    """Test S3 path generation patterns."""

    def test_staging_path_format(self) -> None:
        """Test staging path format: staging/{language}/{voice}/{md5}.mp3"""
        voice = GptVoice.GPT_LT_F1
        md5_hash = "abc123def456"
        language_code = voice.language_code
        voice_path_name = voice.path_name

        staging_path = f"staging/{language_code}/{voice_path_name}/{md5_hash}.mp3"
        self.assertEqual(staging_path, "staging/lt/ruta/abc123def456.mp3")

    def test_prod_path_format(self) -> None:
        """Test production path format: prod/{language}/{voice}/{md5}.mp3"""
        voice = GptVoice.GPT_ZH_M1
        md5_hash = "abc123def456"
        language_code = voice.language_code
        voice_path_name = voice.path_name

        prod_path = f"prod/{language_code}/{voice_path_name}/{md5_hash}.mp3"
        self.assertEqual(prod_path, "prod/zh/zhiyuan/abc123def456.mp3")

    def test_manifest_path_format(self) -> None:
        """Test manifest path format matches audio path with .manifest extension."""
        voice = GptVoice.GPT_ES_F2
        md5_hash = "abc123def456"
        language_code = voice.language_code
        voice_path_name = voice.path_name

        audio_path = f"staging/{language_code}/{voice_path_name}/{md5_hash}.mp3"
        manifest_path = f"staging/{language_code}/{voice_path_name}/{md5_hash}.manifest"

        self.assertEqual(audio_path, "staging/es/carmen/abc123def456.mp3")
        self.assertEqual(manifest_path, "staging/es/carmen/abc123def456.manifest")

    def test_all_voice_paths_are_unique(self) -> None:
        """Test that all voice path_names are unique within each language."""
        for lang in SUPPORTED_LANGUAGES:
            voices = GptVoice.get_voices_for_language(lang)
            path_names = [v.path_name for v in voices]
            self.assertEqual(
                len(path_names),
                len(set(path_names)),
                f"Duplicate path_names found for language {lang}: {path_names}",
            )


if __name__ == "__main__":
    unittest.main()
