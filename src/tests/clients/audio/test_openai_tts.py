#!/usr/bin/env python3
"""
Tests for OpenAI TTS client.

These tests verify the audio generation client works correctly.
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.openai_tts import OpenAITTSClient
from clients.audio.types import Voice, AudioFormat, AudioGenerationResult


class TestOpenAITTSClient(unittest.TestCase):
    """Test OpenAI TTS client functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the API key loading
        self.mock_api_key = "sk-test-key-123"

    @patch("clients.audio.openai_tts.requests.post")
    @patch.object(OpenAITTSClient, "_load_key")
    def test_generate_audio_success(self, mock_load_key, mock_post):
        """Test successful audio generation."""
        mock_load_key.return_value = self.mock_api_key

        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()
        result = client.generate_audio(
            text="labas",
            voice=Voice.ASH,
            language_code="lt"
        )

        # Verify result
        self.assertTrue(result.success)
        self.assertEqual(result.audio_data, b"fake audio data")
        self.assertEqual(result.text, "labas")
        self.assertEqual(result.voice, Voice.ASH)
        self.assertEqual(result.language_code, "lt")
        self.assertIsNone(result.error)

        # Verify API was called correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("json", call_args.kwargs)
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["model"], "gpt-4o-mini-tts")
        self.assertEqual(payload["input"], "labas")
        self.assertEqual(payload["voice"], "ash")
        self.assertIn("instructions", payload)

    @patch("clients.audio.openai_tts.requests.post")
    @patch.object(OpenAITTSClient, "_load_key")
    def test_generate_audio_api_error(self, mock_load_key, mock_post):
        """Test handling of API errors."""
        mock_load_key.return_value = self.mock_api_key

        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()
        result = client.generate_audio(
            text="labas",
            voice=Voice.ASH,
            language_code="lt"
        )

        # Verify error handling
        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertIsNotNone(result.error)
        self.assertIn("429", result.error)

    @patch("clients.audio.openai_tts.requests.post")
    @patch.object(OpenAITTSClient, "_load_key")
    def test_generate_audio_with_speed(self, mock_load_key, mock_post):
        """Test audio generation with custom speed."""
        mock_load_key.return_value = self.mock_api_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()
        result = client.generate_audio(
            text="labas",
            voice=Voice.NOVA,
            language_code="lt",
            speed=0.75
        )

        # Verify speed parameter was included
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["speed"], 0.75)

    @patch("clients.audio.openai_tts.requests.post")
    @patch.object(OpenAITTSClient, "_load_key")
    def test_language_specific_instructions(self, mock_load_key, mock_post):
        """Test that language-specific instructions are used."""
        mock_load_key.return_value = self.mock_api_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()

        # Test Lithuanian
        result = client.generate_audio(text="labas", language_code="lt")
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertIn("Lithuanian", payload["instructions"])

        # Test Chinese
        mock_post.reset_mock()
        result = client.generate_audio(text="你好", language_code="zh")
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertIn("Chinese", payload["instructions"])

    @patch("clients.audio.openai_tts.requests.post")
    @patch.object(OpenAITTSClient, "_load_key")
    def test_audio_format_parameter(self, mock_load_key, mock_post):
        """Test different audio format options."""
        mock_load_key.return_value = self.mock_api_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()

        # Test MP3 format (default)
        result = client.generate_audio(text="test", audio_format=AudioFormat.MP3)
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], "mp3")

        # Test WAV format
        mock_post.reset_mock()
        result = client.generate_audio(text="test", audio_format=AudioFormat.WAV)
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], "wav")

    def test_voice_enum_values(self):
        """Test that Voice enum has correct values."""
        self.assertEqual(Voice.ASH.value, "ash")
        self.assertEqual(Voice.ALLOY.value, "alloy")
        self.assertEqual(Voice.NOVA.value, "nova")
        self.assertEqual(Voice.ONYX.value, "onyx")

    def test_audio_format_enum_values(self):
        """Test that AudioFormat enum has correct values."""
        self.assertEqual(AudioFormat.MP3.value, "mp3")
        self.assertEqual(AudioFormat.WAV.value, "wav")
        self.assertEqual(AudioFormat.OPUS.value, "opus")


class TestAudioGenerationResult(unittest.TestCase):
    """Test AudioGenerationResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = AudioGenerationResult(
            audio_data=b"test data",
            text="test text",
            voice=Voice.ASH,
            language_code="lt",
            model="gpt-4o-mini-tts",
            duration_ms=1500.0,
            success=True,
            error=None
        )

        self.assertTrue(result.success)
        self.assertEqual(result.audio_data, b"test data")
        self.assertEqual(result.text, "test text")
        self.assertEqual(result.voice, Voice.ASH)
        self.assertIsNone(result.error)

    def test_error_result(self):
        """Test creating an error result."""
        result = AudioGenerationResult(
            audio_data=b"",
            text="test text",
            voice=Voice.ASH,
            language_code="lt",
            model="gpt-4o-mini-tts",
            duration_ms=0,
            success=False,
            error="API error"
        )

        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertEqual(result.error, "API error")


if __name__ == "__main__":
    unittest.main()
