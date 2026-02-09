#!/usr/bin/env python3
"""
Tests for Google Cloud Text-to-Speech client.

These tests verify the Google TTS client works correctly using mocked HTTP requests.
"""

import base64
import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.google_tts import (
    GOOGLE_FORMAT_MAP,
    GoogleTTSClient,
    GoogleTtsVoice,
)
from clients.audio.types import AudioFormat, AudioGenerationResult


class TestGoogleTtsVoice(unittest.TestCase):
    """Test GoogleTtsVoice enum properties."""

    def test_voice_name(self) -> None:
        """Test voice_name property."""
        self.assertEqual(GoogleTtsVoice.ZH_WAVENET_A.voice_name, "cmn-CN-Wavenet-A")
        self.assertEqual(GoogleTtsVoice.ES_WAVENET_B.voice_name, "es-ES-Wavenet-B")
        self.assertEqual(GoogleTtsVoice.FR_WAVENET_A.voice_name, "fr-FR-Wavenet-A")

    def test_language_code(self) -> None:
        """Test language_code property."""
        self.assertEqual(GoogleTtsVoice.ZH_WAVENET_A.language_code, "zh")
        self.assertEqual(GoogleTtsVoice.ES_WAVENET_C.language_code, "es")
        self.assertEqual(GoogleTtsVoice.LT_STANDARD_A.language_code, "lt")

    def test_gender(self) -> None:
        """Test gender property."""
        self.assertEqual(GoogleTtsVoice.ZH_WAVENET_A.gender, "f")
        self.assertEqual(GoogleTtsVoice.ES_WAVENET_B.gender, "m")

    def test_voice_type(self) -> None:
        """Test voice_type property."""
        self.assertEqual(GoogleTtsVoice.ZH_WAVENET_A.voice_type, "Wavenet")
        self.assertEqual(GoogleTtsVoice.ES_NEURAL2_A.voice_type, "Neural2")
        self.assertEqual(GoogleTtsVoice.LT_STANDARD_A.voice_type, "Standard")

    def test_ui_name(self) -> None:
        """Test ui_name property."""
        self.assertEqual(GoogleTtsVoice.ZH_WAVENET_A.ui_name, "google-zh_wavenet_a")
        self.assertEqual(GoogleTtsVoice.FR_NEURAL2_A.ui_name, "google-fr_neural2_a")

    def test_google_language_code(self) -> None:
        """Test google_language_code for API calls."""
        self.assertEqual(GoogleTtsVoice.ZH_WAVENET_A.google_language_code, "cmn-CN")
        self.assertEqual(GoogleTtsVoice.ES_WAVENET_B.google_language_code, "es-ES")
        self.assertEqual(GoogleTtsVoice.LT_STANDARD_A.google_language_code, "lt-LT")

    def test_get_voices_for_language(self) -> None:
        """Test filtering voices by language."""
        zh_voices = GoogleTtsVoice.get_voices_for_language("zh")
        self.assertTrue(len(zh_voices) >= 2)
        for v in zh_voices:
            self.assertEqual(v.language_code, "zh")

        lt_voices = GoogleTtsVoice.get_voices_for_language("lt")
        self.assertEqual(len(lt_voices), 1)
        self.assertEqual(lt_voices[0], GoogleTtsVoice.LT_STANDARD_A)

    def test_no_voices_for_unsupported_language(self) -> None:
        """Test that unsupported languages return empty list."""
        voices = GoogleTtsVoice.get_voices_for_language("xx")
        self.assertEqual(len(voices), 0)


class TestGoogleTTSClient(unittest.TestCase):
    """Test GoogleTTSClient functionality."""

    @patch("clients.audio.google_tts.load_key")
    def test_client_init_no_key(self, mock_load_key: MagicMock) -> None:
        """Test client initialization without API key."""
        mock_load_key.return_value = None
        client = GoogleTTSClient()
        self.assertIsNone(client.api_key)

    @patch("clients.audio.google_tts.load_key")
    def test_generate_audio_no_key(self, mock_load_key: MagicMock) -> None:
        """Test audio generation fails gracefully without API key."""
        mock_load_key.return_value = None
        client = GoogleTTSClient()
        result = client.generate_audio(
            text="hello", voice=GoogleTtsVoice.ES_WAVENET_C, language_code="es"
        )
        self.assertFalse(result.success)
        self.assertIn("not available", result.error or "")

    @patch("clients.audio.google_tts.requests.post")
    @patch("clients.audio.google_tts.load_key")
    def test_generate_audio_success(self, mock_load_key: MagicMock, mock_post: MagicMock) -> None:
        """Test successful audio generation."""
        mock_load_key.return_value = "test-api-key"

        # Mock successful API response with base64 audio
        fake_audio = b"fake google audio data"
        encoded_audio = base64.b64encode(fake_audio).decode("utf-8")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"audioContent": encoded_audio}
        mock_post.return_value = mock_response

        client = GoogleTTSClient()
        result = client.generate_audio(
            text="hola", voice=GoogleTtsVoice.ES_WAVENET_C, language_code="es"
        )

        self.assertTrue(result.success)
        self.assertEqual(result.audio_data, fake_audio)
        self.assertEqual(result.text, "hola")
        self.assertEqual(result.language_code, "es")
        self.assertIn("google", result.model)
        self.assertIsNone(result.error)

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["input"]["text"], "hola")
        self.assertEqual(payload["voice"]["name"], "es-ES-Wavenet-C")
        self.assertEqual(payload["voice"]["ssmlGender"], "FEMALE")
        self.assertEqual(payload["audioConfig"]["audioEncoding"], "MP3")

    @patch("clients.audio.google_tts.requests.post")
    @patch("clients.audio.google_tts.load_key")
    def test_generate_audio_api_error(self, mock_load_key: MagicMock, mock_post: MagicMock) -> None:
        """Test handling of API errors."""
        mock_load_key.return_value = "test-api-key"

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_post.return_value = mock_response

        client = GoogleTTSClient()
        result = client.generate_audio(
            text="hola", voice=GoogleTtsVoice.ES_WAVENET_C, language_code="es"
        )

        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertIn("403", result.error or "")

    @patch("clients.audio.google_tts.requests.post")
    @patch("clients.audio.google_tts.load_key")
    def test_generate_audio_with_rate(self, mock_load_key: MagicMock, mock_post: MagicMock) -> None:
        """Test audio generation with custom speaking rate."""
        mock_load_key.return_value = "test-api-key"

        fake_audio = b"audio"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"audioContent": base64.b64encode(fake_audio).decode()}
        mock_post.return_value = mock_response

        client = GoogleTTSClient()
        result = client.generate_audio(
            text="test",
            voice=GoogleTtsVoice.FR_WAVENET_A,
            language_code="fr",
            speaking_rate=0.8,
            pitch=-2.0,
        )

        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["audioConfig"]["speakingRate"], 0.8)
        self.assertEqual(payload["audioConfig"]["pitch"], -2.0)


class TestGoogleFormatMap(unittest.TestCase):
    """Test Google TTS format mapping."""

    def test_mp3_format(self) -> None:
        """Test MP3 format mapping."""
        self.assertEqual(GOOGLE_FORMAT_MAP[AudioFormat.MP3], "MP3")

    def test_wav_format(self) -> None:
        """Test WAV format mapping."""
        self.assertEqual(GOOGLE_FORMAT_MAP[AudioFormat.WAV], "LINEAR16")

    def test_opus_format(self) -> None:
        """Test OPUS format mapping."""
        self.assertEqual(GOOGLE_FORMAT_MAP[AudioFormat.OPUS], "OGG_OPUS")


if __name__ == "__main__":
    unittest.main()
