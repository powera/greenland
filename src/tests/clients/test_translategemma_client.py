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
        # Use Ollama backend for tests (default)
        self.client = TranslateGemmaClient(
            backend="ollama",
            server="localhost",
            port=11434,
            timeout=30,
            debug=False,
            model="translategemma:4b",
        )

    @patch("clients.translategemma_client.requests.post")
    def test_prompt_formatting(self, mock_post: MagicMock) -> None:
        """Test that system and user messages follow TranslateGemma format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "fleur"},
            "total_duration": 500000000,
            "prompt_eval_count": 20,
            "eval_count": 5,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        self.client.generate_translation(
            text="flower",
            source_lang="en",
            target_lang="fr",
        )

        # Verify the request was made
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        request_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        messages = request_data["messages"]
        self.assertEqual(len(messages), 1)

        # Check user message format - verify Ollama professional translator format
        user_msg = messages[0]
        self.assertEqual(user_msg["role"], "user")

        # For Ollama format: professional translator prompt
        self.assertIsInstance(user_msg["content"], str)
        self.assertIn("professional English (en) to French (fr) translator", user_msg["content"])
        self.assertIn("flower", user_msg["content"])
        self.assertIn("Produce only the French translation", user_msg["content"])

        # Check that the model from __init__ is used
        self.assertEqual(request_data["model"], "translategemma:4b")

    @patch("clients.translategemma_client.requests.post")
    def test_generate_chat_extracts_languages_from_context(self, mock_post: MagicMock) -> None:
        """Test that generate_chat parses language pair from context string."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "Blume"},
            "total_duration": 500000000,
            "prompt_eval_count": 20,
            "eval_count": 5,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        self.client.generate_chat(
            prompt="flower",
            context="translate from English to German",
        )

        call_kwargs = mock_post.call_args
        request_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        messages = request_data["messages"]
        user_msg = messages[0]
        # Verify professional translator format contains language info
        self.assertIn("English (en) to German (de)", user_msg["content"])

    @patch("clients.translategemma_client.requests.post")
    def test_json_schema_ignored(self, mock_post: MagicMock) -> None:
        """Test that JSON schema is gracefully ignored."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "fleur"},
            "total_duration": 500000000,
            "prompt_eval_count": 20,
            "eval_count": 5,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        schema = {
            "type": "object",
            "properties": {"translation": {"type": "string"}},
        }

        result = self.client.generate_chat(
            prompt="flower",
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
            "message": {"role": "assistant", "content": "  bonjour  "},
            "total_duration": 300000000,
            "prompt_eval_count": 15,
            "eval_count": 3,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = self.client.generate_translation(
            text="hello",
            source_lang="en",
            target_lang="fr",
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
