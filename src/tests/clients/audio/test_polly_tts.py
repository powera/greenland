#!/usr/bin/env python3
"""
Tests for Amazon Polly TTS client.

These tests verify the Polly TTS client works correctly using mocked boto3 calls.
"""

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.polly_tts import (
    POLLY_LANGUAGE_CODES,
    PollyTTSClient,
    PollyVoice,
    _load_polly_credentials,
)
from clients.audio.types import AudioFormat, AudioGenerationResult


class TestPollyVoice(unittest.TestCase):
    """Test PollyVoice enum properties."""

    def test_voice_id(self) -> None:
        """Test voice_id property."""
        self.assertEqual(PollyVoice.ZHIYU.voice_id, "Zhiyu")
        self.assertEqual(PollyVoice.LUPE.voice_id, "Lupe")
        self.assertEqual(PollyVoice.LEA.voice_id, "Léa")

    def test_language_code(self) -> None:
        """Test language_code property."""
        self.assertEqual(PollyVoice.ZHIYU.language_code, "zh")
        self.assertEqual(PollyVoice.LUPE.language_code, "es")
        self.assertEqual(PollyVoice.LEA.language_code, "fr")

    def test_gender(self) -> None:
        """Test gender property."""
        self.assertEqual(PollyVoice.ZHIYU.gender, "f")
        self.assertEqual(PollyVoice.PEDRO.gender, "m")

    def test_ui_name(self) -> None:
        """Test ui_name property."""
        self.assertEqual(PollyVoice.LUPE.ui_name, "polly-lupe")
        self.assertEqual(PollyVoice.REMI.ui_name, "polly-rémi")

    def test_get_voices_for_language(self) -> None:
        """Test filtering voices by language."""
        es_voices = PollyVoice.get_voices_for_language("es")
        self.assertTrue(len(es_voices) >= 2)
        for v in es_voices:
            self.assertEqual(v.language_code, "es")

        zh_voices = PollyVoice.get_voices_for_language("zh")
        self.assertEqual(len(zh_voices), 1)
        self.assertEqual(zh_voices[0], PollyVoice.ZHIYU)

    def test_no_voices_for_unsupported_language(self) -> None:
        """Test that unsupported languages return empty list."""
        lt_voices = PollyVoice.get_voices_for_language("lt")
        self.assertEqual(len(lt_voices), 0)


class TestPollyTTSClient(unittest.TestCase):
    """Test PollyTTSClient functionality."""

    @patch("clients.audio.polly_tts._load_polly_credentials")
    def test_client_init_no_credentials(self, mock_load: MagicMock) -> None:
        """Test client initialization without credentials."""
        mock_load.return_value = (None, None, "us-east-1")
        client = PollyTTSClient()
        self.assertIsNone(client.polly_client)

    @patch("clients.audio.polly_tts._load_polly_credentials")
    def test_generate_audio_no_client(self, mock_load: MagicMock) -> None:
        """Test audio generation fails gracefully without credentials."""
        mock_load.return_value = (None, None, "us-east-1")
        client = PollyTTSClient()
        result = client.generate_audio(text="hola", voice=PollyVoice.LUPE, language_code="es")
        self.assertFalse(result.success)
        self.assertIn("not initialized", result.error or "")

    @patch("clients.audio.polly_tts._load_polly_credentials")
    def test_generate_audio_success(self, mock_load: MagicMock) -> None:
        """Test successful audio generation."""
        mock_load.return_value = (None, None, "us-east-1")

        # Create client without boto3, then inject a mock polly_client
        client = PollyTTSClient()

        mock_polly = MagicMock()
        mock_audio_stream = MagicMock()
        mock_audio_stream.read.return_value = b"fake polly audio"
        mock_polly.synthesize_speech.return_value = {"AudioStream": mock_audio_stream}
        client.polly_client = mock_polly

        result = client.generate_audio(text="hola", voice=PollyVoice.LUPE, language_code="es")

        self.assertTrue(result.success)
        self.assertEqual(result.audio_data, b"fake polly audio")
        self.assertEqual(result.text, "hola")
        self.assertEqual(result.language_code, "es")
        self.assertIn("polly", result.model)
        self.assertIsNone(result.error)

        # Verify API call
        mock_polly.synthesize_speech.assert_called_once()
        call_kwargs = mock_polly.synthesize_speech.call_args.kwargs
        self.assertEqual(call_kwargs["Text"], "hola")
        self.assertEqual(call_kwargs["VoiceId"], "Lupe")
        self.assertEqual(call_kwargs["Engine"], "neural")

    @patch("clients.audio.polly_tts._load_polly_credentials")
    def test_generate_audio_api_error(self, mock_load: MagicMock) -> None:
        """Test handling of API errors."""
        mock_load.return_value = (None, None, "us-east-1")

        client = PollyTTSClient()

        mock_polly = MagicMock()
        mock_polly.synthesize_speech.side_effect = Exception("Polly API error")
        client.polly_client = mock_polly

        result = client.generate_audio(text="hola", voice=PollyVoice.LUPE, language_code="es")

        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertIn("Polly API error", result.error or "")


class TestPollyLanguageCodes(unittest.TestCase):
    """Test Polly language code mapping."""

    def test_known_mappings(self) -> None:
        """Test known language code mappings."""
        self.assertEqual(POLLY_LANGUAGE_CODES["zh"], "cmn-CN")
        self.assertEqual(POLLY_LANGUAGE_CODES["es"], "es-ES")
        self.assertEqual(POLLY_LANGUAGE_CODES["fr"], "fr-FR")

    def test_missing_language(self) -> None:
        """Test that Lithuanian is not in the mapping."""
        self.assertNotIn("lt", POLLY_LANGUAGE_CODES)


if __name__ == "__main__":
    unittest.main()
