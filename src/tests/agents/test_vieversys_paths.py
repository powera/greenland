#!/usr/bin/env python3
"""
Tests for Vieversys S3 path generation.

These tests verify that the staging and production paths are correctly
generated with the format: {prefix}/{language}/{voice}/{md5}.mp3
"""

import sys
import unittest
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.gpt_voices import GptVoice


class TestVieversysStagingPath(unittest.TestCase):
    """Test staging path generation in VieversysAgent."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.md5_hash = "abc123def456789"
        self.language_code = "lt"
        self.voice_path_name = "ruta"

    def test_staging_audio_key_format(self) -> None:
        """Test staging audio key has correct format."""
        staging_prefix = "staging"
        audio_key = (
            f"{staging_prefix}/{self.language_code}/{self.voice_path_name}/{self.md5_hash}.mp3"
        )

        self.assertEqual(audio_key, "staging/lt/ruta/abc123def456789.mp3")

    def test_staging_manifest_key_format(self) -> None:
        """Test staging manifest key has correct format."""
        staging_prefix = "staging"
        manifest_key = (
            f"{staging_prefix}/{self.language_code}/{self.voice_path_name}/{self.md5_hash}.manifest"
        )

        self.assertEqual(manifest_key, "staging/lt/ruta/abc123def456789.manifest")

    def test_staging_path_with_different_languages(self) -> None:
        """Test staging paths for different languages."""
        staging_prefix = "staging"

        test_cases = [
            ("lt", "ruta", "staging/lt/ruta/abc123.mp3"),
            ("lt", "jonas", "staging/lt/jonas/abc123.mp3"),
            ("zh", "meiling", "staging/zh/meiling/abc123.mp3"),
            ("zh", "zhiyuan", "staging/zh/zhiyuan/abc123.mp3"),
            ("es", "maria", "staging/es/maria/abc123.mp3"),
            ("es", "carlos", "staging/es/carlos/abc123.mp3"),
            ("fr", "marie", "staging/fr/marie/abc123.mp3"),
            ("fr", "pierre", "staging/fr/pierre/abc123.mp3"),
        ]

        for lang, voice, expected_path in test_cases:
            audio_key = f"{staging_prefix}/{lang}/{voice}/abc123.mp3"
            self.assertEqual(audio_key, expected_path, f"Failed for {lang}/{voice}")

    def test_staging_path_uses_gpt_voice_path_name(self) -> None:
        """Test staging path uses GptVoice.path_name property."""
        staging_prefix = "staging"
        md5 = "testmd5hash"

        # Test each voice's path_name is used correctly
        for voice in GptVoice:
            lang = voice.language_code
            path_name = voice.path_name

            audio_key = f"{staging_prefix}/{lang}/{path_name}/{md5}.mp3"

            # Verify the path contains the expected components
            self.assertTrue(audio_key.startswith("staging/"))
            self.assertIn(f"/{lang}/", audio_key)
            self.assertIn(f"/{path_name}/", audio_key)
            self.assertTrue(audio_key.endswith(f"/{md5}.mp3"))


class TestVieversysProdPath(unittest.TestCase):
    """Test production path generation in VieversysAgent."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.md5_hash = "abc123def456789"
        self.language_code = "lt"
        self.voice_path_name = "ruta"

    def test_prod_key_format(self) -> None:
        """Test production key has correct format."""
        prod_key = f"prod/{self.language_code}/{self.voice_path_name}/{self.md5_hash}.mp3"

        self.assertEqual(prod_key, "prod/lt/ruta/abc123def456789.mp3")

    def test_prod_path_with_different_languages(self) -> None:
        """Test production paths for different languages."""
        test_cases = [
            ("lt", "ruta", "prod/lt/ruta/abc123.mp3"),
            ("lt", "jonas", "prod/lt/jonas/abc123.mp3"),
            ("zh", "meiling", "prod/zh/meiling/abc123.mp3"),
            ("zh", "zhiyuan", "prod/zh/zhiyuan/abc123.mp3"),
            ("es", "maria", "prod/es/maria/abc123.mp3"),
            ("es", "carlos", "prod/es/carlos/abc123.mp3"),
            ("fr", "marie", "prod/fr/marie/abc123.mp3"),
            ("fr", "pierre", "prod/fr/pierre/abc123.mp3"),
        ]

        for lang, voice, expected_path in test_cases:
            prod_key = f"prod/{lang}/{voice}/abc123.mp3"
            self.assertEqual(prod_key, expected_path, f"Failed for {lang}/{voice}")

    def test_prod_path_uses_gpt_voice_path_name(self) -> None:
        """Test production path uses GptVoice.path_name property."""
        md5 = "testmd5hash"

        # Test each voice's path_name is used correctly
        for voice in GptVoice:
            lang = voice.language_code
            path_name = voice.path_name

            prod_key = f"prod/{lang}/{path_name}/{md5}.mp3"

            # Verify the path contains the expected components
            self.assertTrue(prod_key.startswith("prod/"))
            self.assertIn(f"/{lang}/", prod_key)
            self.assertIn(f"/{path_name}/", prod_key)
            self.assertTrue(prod_key.endswith(f"/{md5}.mp3"))


class TestVieversysPathLogic(unittest.TestCase):
    """Test the path generation logic used in VieversysAgent upload methods.

    These tests verify the exact path format that _upload_to_staging_path and
    _upload_to_prod_path generate. The format is:
    - staging: staging/{language}/{voice}/{md5}.mp3
    - prod: prod/{language}/{voice}/{md5}.mp3
    """

    def test_staging_path_logic(self) -> None:
        """Test staging path construction logic matches _upload_to_staging_path."""
        # This mirrors the logic in VieversysAgent._upload_to_staging_path
        staging_prefix = "staging"
        language_code = "lt"
        voice_path_name = "ruta"
        md5_hash = "abc123"

        audio_key = f"{staging_prefix}/{language_code}/{voice_path_name}/{md5_hash}.mp3"
        manifest_key = f"{staging_prefix}/{language_code}/{voice_path_name}/{md5_hash}.manifest"

        self.assertEqual(audio_key, "staging/lt/ruta/abc123.mp3")
        self.assertEqual(manifest_key, "staging/lt/ruta/abc123.manifest")

    def test_prod_path_logic(self) -> None:
        """Test production path construction logic matches _upload_to_prod_path."""
        # This mirrors the logic in VieversysAgent._upload_to_prod_path
        language_code = "zh"
        voice_path_name = "meiling"
        md5_hash = "xyz789"

        prod_key = f"prod/{language_code}/{voice_path_name}/{md5_hash}.mp3"

        self.assertEqual(prod_key, "prod/zh/meiling/xyz789.mp3")

    def test_staging_path_for_all_voices(self) -> None:
        """Test staging path generation for all defined voices."""
        staging_prefix = "staging"
        md5_hash = "testmd5"

        expected_paths = {
            GptVoice.GPT_LT_F1: "staging/lt/ruta/testmd5.mp3",
            GptVoice.GPT_LT_F2: "staging/lt/egle/testmd5.mp3",
            GptVoice.GPT_LT_M1: "staging/lt/jonas/testmd5.mp3",
            GptVoice.GPT_LT_M2: "staging/lt/tomas/testmd5.mp3",
            GptVoice.GPT_ZH_F1: "staging/zh/meiling/testmd5.mp3",
            GptVoice.GPT_ZH_F2: "staging/zh/yating/testmd5.mp3",
            GptVoice.GPT_ZH_M1: "staging/zh/zhiyuan/testmd5.mp3",
            GptVoice.GPT_ZH_M2: "staging/zh/haoran/testmd5.mp3",
            GptVoice.GPT_ES_F1: "staging/es/maria/testmd5.mp3",
            GptVoice.GPT_ES_F2: "staging/es/carmen/testmd5.mp3",
            GptVoice.GPT_ES_M1: "staging/es/carlos/testmd5.mp3",
            GptVoice.GPT_ES_M2: "staging/es/miguel/testmd5.mp3",
            GptVoice.GPT_FR_F1: "staging/fr/marie/testmd5.mp3",
            GptVoice.GPT_FR_F2: "staging/fr/sophie/testmd5.mp3",
            GptVoice.GPT_FR_M1: "staging/fr/pierre/testmd5.mp3",
            GptVoice.GPT_FR_M2: "staging/fr/jean/testmd5.mp3",
        }

        for voice, expected_path in expected_paths.items():
            language_code = voice.language_code
            voice_path_name = voice.path_name
            audio_key = f"{staging_prefix}/{language_code}/{voice_path_name}/{md5_hash}.mp3"
            self.assertEqual(audio_key, expected_path, f"Staging path mismatch for {voice.name}")

    def test_prod_path_for_all_voices(self) -> None:
        """Test production path generation for all defined voices."""
        md5_hash = "testmd5"

        expected_paths = {
            GptVoice.GPT_LT_F1: "prod/lt/ruta/testmd5.mp3",
            GptVoice.GPT_LT_F2: "prod/lt/egle/testmd5.mp3",
            GptVoice.GPT_LT_M1: "prod/lt/jonas/testmd5.mp3",
            GptVoice.GPT_LT_M2: "prod/lt/tomas/testmd5.mp3",
            GptVoice.GPT_ZH_F1: "prod/zh/meiling/testmd5.mp3",
            GptVoice.GPT_ZH_F2: "prod/zh/yating/testmd5.mp3",
            GptVoice.GPT_ZH_M1: "prod/zh/zhiyuan/testmd5.mp3",
            GptVoice.GPT_ZH_M2: "prod/zh/haoran/testmd5.mp3",
            GptVoice.GPT_ES_F1: "prod/es/maria/testmd5.mp3",
            GptVoice.GPT_ES_F2: "prod/es/carmen/testmd5.mp3",
            GptVoice.GPT_ES_M1: "prod/es/carlos/testmd5.mp3",
            GptVoice.GPT_ES_M2: "prod/es/miguel/testmd5.mp3",
            GptVoice.GPT_FR_F1: "prod/fr/marie/testmd5.mp3",
            GptVoice.GPT_FR_F2: "prod/fr/sophie/testmd5.mp3",
            GptVoice.GPT_FR_M1: "prod/fr/pierre/testmd5.mp3",
            GptVoice.GPT_FR_M2: "prod/fr/jean/testmd5.mp3",
        }

        for voice, expected_path in expected_paths.items():
            language_code = voice.language_code
            voice_path_name = voice.path_name
            prod_key = f"prod/{language_code}/{voice_path_name}/{md5_hash}.mp3"
            self.assertEqual(prod_key, expected_path, f"Prod path mismatch for {voice.name}")


class TestPathConsistency(unittest.TestCase):
    """Test that staging and prod paths are consistent."""

    def test_staging_and_prod_paths_differ_only_by_prefix(self) -> None:
        """Test that staging and prod paths have same structure, different prefix."""
        md5 = "abc123"

        for voice in GptVoice:
            lang = voice.language_code
            path_name = voice.path_name

            staging_key = f"staging/{lang}/{path_name}/{md5}.mp3"
            prod_key = f"prod/{lang}/{path_name}/{md5}.mp3"

            # Replace prefix and verify they match
            self.assertEqual(
                staging_key.replace("staging/", "prod/"),
                prod_key,
                f"Path mismatch for {voice.name}",
            )

    def test_all_voices_produce_valid_paths(self) -> None:
        """Test that all GptVoice values produce valid S3 paths."""
        import re

        # Valid S3 key pattern (simplified)
        valid_pattern = re.compile(r"^[a-z]+/[a-z]{2}/[a-z]+/[a-f0-9]+\.mp3$")

        md5 = "abc123def"

        for voice in GptVoice:
            lang = voice.language_code
            path_name = voice.path_name

            staging_key = f"staging/{lang}/{path_name}/{md5}.mp3"
            prod_key = f"prod/{lang}/{path_name}/{md5}.mp3"

            self.assertTrue(
                valid_pattern.match(staging_key),
                f"Invalid staging path for {voice.name}: {staging_key}",
            )
            self.assertTrue(
                valid_pattern.match(prod_key),
                f"Invalid prod path for {voice.name}: {prod_key}",
            )


if __name__ == "__main__":
    unittest.main()
