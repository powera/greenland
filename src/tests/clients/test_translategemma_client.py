#!/usr/bin/python3
"""Unit tests for TranslateGemma client."""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients.translategemma_client import TranslateGemmaClient


class TranslateGemmaClientTestCase(unittest.TestCase):
    """Tests for TranslateGemma client."""

    def setUp(self) -> None:
        self.client = TranslateGemmaClient(server="localhost", port=9054, timeout=30, debug=False)

    @patch("clients.translategemma_client.requests.post")
    def test_prompt_formatting(self, mock_post: MagicMock) -> None:
        """Test that system and user messages follow TranslateGemma format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "fleur"}}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 5,
            },
        }
        mock_response.elapsed.total_seconds.return_value = 0.5
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        self.client.generate_translation(
            text="flower",
            source_lang="en",
            target_lang="fr",
            model="translate-gemma-3-4b-it",
        )

        # Verify the request was made
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        request_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        messages = request_data["messages"]
        self.assertEqual(len(messages), 2)

        # Check system message format
        system_msg = messages[0]
        self.assertEqual(system_msg["role"], "system")
        self.assertIn("English", system_msg["content"])
        self.assertIn("French", system_msg["content"])
        self.assertIn("professional translator", system_msg["content"])

        # Check user message has two blank lines before text
        user_msg = messages[1]
        self.assertEqual(user_msg["role"], "user")
        self.assertTrue(user_msg["content"].startswith("\n\n"))
        self.assertIn("flower", user_msg["content"])

    @patch("clients.translategemma_client.requests.post")
    def test_generate_chat_extracts_languages_from_context(self, mock_post: MagicMock) -> None:
        """Test that generate_chat parses language pair from context string."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Blume"}}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 5,
            },
        }
        mock_response.elapsed.total_seconds.return_value = 0.5
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        self.client.generate_chat(
            prompt="flower",
            model="translate-gemma-3-4b-it",
            context="translate from English to German",
        )

        call_kwargs = mock_post.call_args
        request_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        messages = request_data["messages"]
        system_msg = messages[0]
        self.assertIn("English", system_msg["content"])
        self.assertIn("German", system_msg["content"])

    @patch("clients.translategemma_client.requests.post")
    def test_json_schema_ignored(self, mock_post: MagicMock) -> None:
        """Test that JSON schema is gracefully ignored."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "fleur"}}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 5,
            },
        }
        mock_response.elapsed.total_seconds.return_value = 0.5
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        schema = {
            "type": "object",
            "properties": {"translation": {"type": "string"}},
        }

        result = self.client.generate_chat(
            prompt="flower",
            model="translate-gemma-3-4b-it",
            json_schema=schema,
        )

        # Should still return plain text, not structured data
        self.assertEqual(result.response_text, "fleur")
        self.assertEqual(result.structured_data, {})

        # Verify no response_format was sent in the request
        call_kwargs = mock_post.call_args
        request_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertNotIn("response_format", request_data)

    @patch("clients.translategemma_client.requests.post")
    def test_response_structure(self, mock_post: MagicMock) -> None:
        """Test that response has plain text and empty structured_data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "  bonjour  "}}],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 3,
            },
        }
        mock_response.elapsed.total_seconds.return_value = 0.3
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = self.client.generate_translation(
            text="hello",
            source_lang="en",
            target_lang="fr",
            model="translate-gemma-3-4b-it",
        )

        # Plain text should be stripped
        self.assertEqual(result.response_text, "bonjour")
        self.assertEqual(result.structured_data, {})
        self.assertIsNotNone(result.usage)

    def test_extract_language_pair_from_names(self) -> None:
        """Test language pair extraction with full language names."""
        result = self.client._extract_language_pair("translate from English to French")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "en")
        self.assertEqual(result[1], "fr")

    def test_extract_language_pair_from_codes(self) -> None:
        """Test language pair extraction with 2-letter codes."""
        result = self.client._extract_language_pair("en to zh")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "en")
        self.assertEqual(result[1], "zh")

    def test_extract_language_pair_returns_none_for_invalid(self) -> None:
        """Test that invalid context returns None."""
        result = self.client._extract_language_pair("just some random text")
        self.assertIsNone(result)

    def test_unknown_language_code_raises(self) -> None:
        """Test that unknown language code raises ValueError."""
        with self.assertRaises(ValueError):
            self.client._get_language_name("xx")


if __name__ == "__main__":
    unittest.main()
