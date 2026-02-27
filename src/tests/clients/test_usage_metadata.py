#!/usr/bin/python3
"""Tests for provider-specific usage metadata capture."""

import os
import sys
from typing import Any, Dict, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients.anthropic.client import AnthropicClient
from clients.openai.client import OpenAIClient


def test_openai_usage_includes_reasoning_and_cache_tokens() -> None:
    """OpenAI usage metadata should preserve detailed token counters."""
    client = OpenAIClient.__new__(OpenAIClient)
    client.timeout = 50
    client.debug = False
    client.api_key = "test-key"
    client.headers = {"Authorization": "Bearer test-key", "Content-Type": "application/json"}

    def _fake_response(**kwargs: Any) -> Tuple[Dict[str, Any], float]:
        return (
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 50,
                    "input_tokens_details": {"cached_tokens": 80},
                    "output_tokens_details": {"reasoning_tokens": 17},
                },
            },
            1.5,
        )

    client._create_response = _fake_response  # type: ignore[method-assign]
    response = client.generate_chat(prompt="hi", model="gpt-5-mini")

    assert response.usage is not None
    assert response.usage.metadata["cached_tokens"] == 80
    assert response.usage.metadata["reasoning_tokens"] == 17


def test_anthropic_usage_includes_cache_token_counters() -> None:
    """Anthropic usage metadata should preserve prompt-cache accounting."""
    client = AnthropicClient(api_key="test-key", debug=False)

    def _fake_response(**kwargs: Any) -> Tuple[Dict[str, Any], float]:
        return (
            {
                "content": [{"type": "text", "text": "ok"}],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 60,
                    "cache_read_input_tokens": 40,
                },
            },
            2.0,
        )

    client._create_message = _fake_response  # type: ignore[method-assign]
    response = client.generate_chat(prompt="hi", model="claude-haiku-4-5")

    assert response.usage is not None
    assert response.usage.metadata["cache_creation_input_tokens"] == 60
    assert response.usage.metadata["cache_read_input_tokens"] == 40
