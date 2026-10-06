#!/usr/bin/python3
"""Prompt-cache token counts, as each backend reports them, and their pricing.

Every provider reports cache hits in its own place -- and Anthropic leaves them
out of input_tokens altogether -- so each client test stubs the outbound-request
method with the provider's own usage shape and checks that tokens_in stays the
whole prompt with cached_tokens_in as a breakdown of it.  Nothing here can reach
the network.
"""

from typing import Any, Dict

import pytest

from clients.anthropic.client import AnthropicClient
from clients.digitalocean_client import DigitalOceanClient
from clients.gemini_client import GeminiClient
from clients.openai.client import OpenAIClient
from util.telemetry import CostConfig, LLMUsage


def test_openai_reads_cached_tokens_from_input_details() -> None:
    client = OpenAIClient()
    client.api_key = "test-key-not-used"
    envelope: Dict[str, Any] = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
        "usage": {
            "input_tokens": 3000,
            "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 2048, "cache_write_tokens": 512},
        },
    }
    client._create_response = lambda **kwargs: (envelope, 1.0)  # type: ignore[method-assign]

    usage = client.generate_chat(prompt="hi", model="gpt-6-luna").usage

    assert usage is not None
    assert usage.tokens_in == 3000
    assert usage.cached_tokens_in == 2048
    assert usage.cache_write_tokens_in == 512
    # 440 uncached at $0.10/M, 2048 cached at $0.01/M, 512 written at
    # $0.125/M, 100 out at $0.50/M.
    assert usage.cost == pytest.approx(
        (440 * 0.10 + 2048 * 0.01 + 512 * 0.125 + 100 * 0.50) / 1_000_000
    )


def test_openai_without_input_details_reports_no_cache_hit() -> None:
    client = OpenAIClient()
    client.api_key = "test-key-not-used"
    envelope: Dict[str, Any] = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
        "usage": {"input_tokens": 3000, "output_tokens": 100},
    }
    client._create_response = lambda **kwargs: (envelope, 1.0)  # type: ignore[method-assign]

    usage = client.generate_chat(prompt="hi", model="gpt-6-luna").usage

    assert usage is not None
    assert usage.cached_tokens_in == 0


def test_anthropic_adds_cache_reads_and_writes_into_tokens_in() -> None:
    client = AnthropicClient(api_key="test-key-not-used")
    message: Dict[str, Any] = {
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 50,
            "output_tokens": 10,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 300,
        },
    }
    client._create_message = lambda **kwargs: (message, 1.0)  # type: ignore[method-assign]

    usage = client.generate_chat(prompt="hi", model="claude-3-5-haiku-latest").usage

    assert usage is not None
    assert usage.tokens_in == 2350
    assert usage.cached_tokens_in == 2000
    assert usage.cache_write_tokens_in == 300
    assert usage.cost == pytest.approx((50 * 0.8 + 2000 * 0.08 + 300 * 1.0 + 10 * 4) / 1_000_000)


def test_gemini_reads_cached_content_token_count() -> None:
    client = GeminiClient(api_key="test-key-not-used")
    completion: Dict[str, Any] = {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
        "usageMetadata": {
            "promptTokenCount": 3000,
            "candidatesTokenCount": 10,
            "cachedContentTokenCount": 1500,
        },
    }
    client._create_completion = lambda model, **kwargs: (completion, 1.0)  # type: ignore[method-assign]

    usage = client.generate_chat(prompt="hi", model="gemini-3.5-flash-lite").usage

    assert usage is not None
    assert usage.tokens_in == 3000
    assert usage.cached_tokens_in == 1500


def test_digitalocean_reads_cached_tokens_from_prompt_details() -> None:
    client = DigitalOceanClient(api_key="sk-do-test")
    completion: Dict[str, Any] = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 3000,
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 1024},
        },
    }
    client._create_completion = lambda **kwargs: (completion, 1.0)  # type: ignore[method-assign]

    usage = client.generate_chat(prompt="hi", model="llama-4-maverick").usage

    assert usage is not None
    assert usage.tokens_in == 3000
    assert usage.cached_tokens_in == 1024


def test_model_without_a_cached_rate_prices_cache_hits_at_the_input_rate() -> None:
    """A missing rate must never make a cache hit look free."""
    cached = CostConfig.estimate_cost(
        tokens_in=1_000_000, tokens_out=0, model="llama-4-maverick", cached_tokens_in=1_000_000
    )
    uncached = CostConfig.estimate_cost(tokens_in=1_000_000, tokens_out=0, model="llama-4-maverick")
    assert cached == pytest.approx(uncached)


def test_combine_sums_cache_counts() -> None:
    first = LLMUsage(10, 1, 0.0, 1.0, cached_tokens_in=4, cache_write_tokens_in=2)
    second = LLMUsage(20, 1, 0.0, 1.0, cached_tokens_in=8)
    combined = first.combine(second)
    assert combined.cached_tokens_in == 12
    assert combined.cache_write_tokens_in == 2
