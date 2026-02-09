#!/usr/bin/env python3
"""
Tests for Azure Cognitive Services TTS client.

These tests verify the Azure TTS client works correctly using mocked HTTP requests.
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

from clients.audio.azure_tts import (
    AzureTTSClient,
    AzureVoice,
    _escape_xml,
    _load_azure_credentials,
)
from clients.audio.types import AudioFormat, AudioGenerationResult


class TestAzureVoice(unittest.TestCase):
    """Test AzureVoice enum properties."""

    def test_voice_name(self) -> None:
        """Test voice_name property."""
        self.assertEqual(AzureVoice.ONA.voice_name, "lt-LT-OnaNeural")
        self.assertEqual(AzureVoice.XIAOXIAO.voice_name, "zh-CN-XiaoxiaoNeural")
        self.assertEqual(AzureVoice.ELVIRA.voice_name, "es-ES-ElviraNeural")

    def test_language_code(self) -> None:
        """Test language_code property."""
        self.assertEqual(AzureVoice.ONA.language_code, "lt")
        self.assertEqual(AzureVoice.XIAOXIAO.language_code, "zh")
        self.assertEqual(AzureVoice.DENISE.language_code, "fr")

    def test_gender(self) -> None:
        """Test gender property."""
        self.assertEqual(AzureVoice.ONA.gender, "f")
        self.assertEqual(AzureVoice.LEONAS.gender, "m")

    def test_ui_name(self) -> None:
        """Test ui_name property."""
        self.assertEqual(AzureVoice.ONA.ui_name, "azure-ona")
        self.assertEqual(AzureVoice.ELVIRA.ui_name, "azure-elvira")

    def test_get_voices_for_language(self) -> None:
        """Test filtering voices by language."""
        lt_voices = AzureVoice.get_voices_for_language("lt")
        self.assertEqual(len(lt_voices), 2)
        names = {v.name for v in lt_voices}
        self.assertIn("ONA", names)
        self.assertIn("LEONAS", names)

        zh_voices = AzureVoice.get_voices_for_language("zh")
        self.assertTrue(len(zh_voices) >= 2)

    def test_get_voices_for_unsupported_language(self) -> None:
        """Test that unsupported languages return empty list."""
        voices = AzureVoice.get_voices_for_language("xx")
        self.assertEqual(len(voices), 0)


class TestAzureTTSClient(unittest.TestCase):
    """Test AzureTTSClient functionality."""

    @patch("clients.audio.azure_tts._load_azure_credentials")
    def test_client_init_no_credentials(self, mock_load: MagicMock) -> None:
        """Test client initialization without credentials."""
        mock_load.return_value = (None, "eastus")
        client = AzureTTSClient()
        self.assertIsNone(client.subscription_key)

    @patch("clients.audio.azure_tts._load_azure_credentials")
    def test_generate_audio_no_key(self, mock_load: MagicMock) -> None:
        """Test audio generation fails gracefully without credentials."""
        mock_load.return_value = (None, "eastus")
        client = AzureTTSClient()
        result = client.generate_audio(text="labas", voice=AzureVoice.ONA, language_code="lt")
        self.assertFalse(result.success)
        self.assertIn("not available", result.error or "")

    @patch("clients.audio.azure_tts.requests.post")
    @patch("clients.audio.azure_tts._load_azure_credentials")
    def test_generate_audio_success(self, mock_load: MagicMock, mock_post: MagicMock) -> None:
        """Test successful audio generation."""
        mock_load.return_value = ("test-key-123", "eastus")

        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake azure audio"
        mock_post.return_value = mock_response

        client = AzureTTSClient()
        result = client.generate_audio(text="labas", voice=AzureVoice.ONA, language_code="lt")

        self.assertTrue(result.success)
        self.assertEqual(result.audio_data, b"fake azure audio")
        self.assertEqual(result.text, "labas")
        self.assertEqual(result.language_code, "lt")
        self.assertEqual(result.model, "azure-neural")
        self.assertIsNone(result.error)

        # Verify request was made with SSML
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("Ocp-Apim-Subscription-Key", call_args.kwargs["headers"])
        ssml_body = call_args.kwargs["data"].decode("utf-8")
        self.assertIn("lt-LT-OnaNeural", ssml_body)
        self.assertIn("labas", ssml_body)

    @patch("clients.audio.azure_tts.requests.post")
    @patch("clients.audio.azure_tts._load_azure_credentials")
    def test_generate_audio_api_error(self, mock_load: MagicMock, mock_post: MagicMock) -> None:
        """Test handling of API errors."""
        mock_load.return_value = ("test-key-123", "eastus")

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        client = AzureTTSClient()
        result = client.generate_audio(text="labas", voice=AzureVoice.ONA, language_code="lt")

        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertIn("401", result.error or "")

    @patch("clients.audio.azure_tts.requests.post")
    @patch("clients.audio.azure_tts._load_azure_credentials")
    def test_generate_audio_with_rate(self, mock_load: MagicMock, mock_post: MagicMock) -> None:
        """Test audio generation with custom rate."""
        mock_load.return_value = ("test-key-123", "eastus")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio"
        mock_post.return_value = mock_response

        client = AzureTTSClient()
        result = client.generate_audio(
            text="labas", voice=AzureVoice.ONA, language_code="lt", rate="-20%"
        )

        # Verify SSML includes prosody rate
        call_args = mock_post.call_args
        ssml_body = call_args.kwargs["data"].decode("utf-8")
        self.assertIn('rate="-20%"', ssml_body)


class TestEscapeXml(unittest.TestCase):
    """Test XML escaping utility."""

    def test_basic_escaping(self) -> None:
        """Test basic XML special character escaping."""
        self.assertEqual(_escape_xml("a & b"), "a &amp; b")
        self.assertEqual(_escape_xml("a < b"), "a &lt; b")
        self.assertEqual(_escape_xml("a > b"), "a &gt; b")

    def test_no_escaping_needed(self) -> None:
        """Test text with no special characters."""
        self.assertEqual(_escape_xml("hello world"), "hello world")

    def test_quotes(self) -> None:
        """Test quote escaping."""
        self.assertEqual(_escape_xml('say "hello"'), "say &quot;hello&quot;")
        self.assertEqual(_escape_xml("it's"), "it&apos;s")


if __name__ == "__main__":
    unittest.main()
