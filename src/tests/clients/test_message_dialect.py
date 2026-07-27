"""Tests for multi-message ("dialect") chat support across LLM clients.

Covers:
- ``normalize_alternating_messages`` (the role-alternation helper).
- Each cloud client mapping a provider-neutral message list into its own
  request shape (with ack insertion where the provider requires alternation).
- ``UnifiedLLMClient`` forwarding ``messages`` to cloud backends and rejecting
  it for local backends.
"""

import sys
import types
from typing import Any, Dict, Iterator, List, Tuple

import pytest

from clients.lib import ChatMessage, normalize_alternating_messages


@pytest.fixture(autouse=True)
def _stub_tiktoken(monkeypatch: Any) -> Iterator[None]:
    """Stub tiktoken so OpenAI/Gemini clients construct without network access.

    Both clients build a ``tiktoken`` encoder in ``__init__``, which otherwise
    downloads encoding data. Tests here never tokenize, so a no-op encoder is
    sufficient.
    """
    fake = types.ModuleType("tiktoken")
    fake.get_encoding = lambda name: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tiktoken", fake)
    yield


def _roles(messages: List[ChatMessage]) -> List[str]:
    return [message["role"] for message in messages]


class TestNormalizeAlternatingMessages:
    def test_empty(self) -> None:
        assert normalize_alternating_messages([]) == []

    def test_single_message_unchanged(self) -> None:
        msgs = [{"role": "user", "content": "a"}]
        assert normalize_alternating_messages(msgs) == msgs

    def test_already_alternating_unchanged(self) -> None:
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        assert normalize_alternating_messages(msgs) == msgs

    def test_consecutive_user_gets_assistant_ack(self) -> None:
        msgs = [
            {"role": "user", "content": "src1"},
            {"role": "user", "content": "src2"},
            {"role": "user", "content": "instruction"},
        ]
        out = normalize_alternating_messages(msgs)
        assert _roles(out) == ["user", "assistant", "user", "assistant", "user"]
        # Original user contents are preserved in order.
        assert [m["content"] for m in out if m["role"] == "user"] == [
            "src1",
            "src2",
            "instruction",
        ]

    def test_consecutive_assistant_gets_user_ack(self) -> None:
        msgs = [
            {"role": "assistant", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        out = normalize_alternating_messages(msgs)
        assert _roles(out) == ["assistant", "user", "assistant"]

    def test_input_not_mutated(self) -> None:
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
        ]
        normalize_alternating_messages(msgs)
        assert len(msgs) == 2


def _two_user_messages() -> List[ChatMessage]:
    return [
        {"role": "user", "content": "Source 1: x"},
        {"role": "user", "content": "Write the entry."},
    ]


def test_anthropic_normalizes_consecutive_user_messages(monkeypatch: Any) -> None:
    from clients.anthropic.client import AnthropicClient

    client = AnthropicClient(api_key="test-key")
    captured: Dict[str, Any] = {}

    def fake_create_message(**kwargs: Any) -> Tuple[Dict[str, Any], float]:
        captured.update(kwargs)
        data = {
            "content": [{"type": "text", "text": "BODY"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        return data, 1.0

    monkeypatch.setattr(client, "_create_message", fake_create_message)

    result = client.generate_chat("", model="claude-test", messages=_two_user_messages())

    assert result.response_text == "BODY"
    # Consecutive user messages must be separated by a synthetic assistant turn.
    assert _roles(captured["messages"]) == ["user", "assistant", "user"]
    assert captured["messages"][0]["content"] == "Source 1: x"
    assert captured["messages"][2]["content"] == "Write the entry."


def test_gemini_maps_roles_and_normalizes(monkeypatch: Any) -> None:
    from clients.gemini_client import GeminiClient

    client = GeminiClient(api_key="test-key")
    captured: Dict[str, Any] = {}

    def fake_create_completion(model: str, **kwargs: Any) -> Tuple[Dict[str, Any], float]:
        captured.update(kwargs)
        data = {
            "candidates": [{"content": {"parts": [{"text": "BODY"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }
        return data, 1.0

    monkeypatch.setattr(client, "_create_completion", fake_create_completion)

    result = client.generate_chat("", model="gemini-test", messages=_two_user_messages())

    assert result.response_text == "BODY"
    contents = captured["contents"]
    # assistant ack inserted, mapped to Gemini's "model" role.
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[0]["parts"][0]["text"] == "Source 1: x"


def test_gemini_35_flash_lite_uses_minimal_thinking(monkeypatch: Any) -> None:
    from clients.gemini_client import GeminiClient

    client = GeminiClient(api_key="test-key")
    captured: Dict[str, Any] = {}

    def fake_create_completion(model: str, **kwargs: Any) -> Tuple[Dict[str, Any], float]:
        captured.update(kwargs)
        data = {
            "candidates": [{"content": {"parts": [{"text": "BODY"}]}}],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 20,
                "thoughtsTokenCount": 5,
            },
        }
        return data, 1.0

    monkeypatch.setattr(client, "_create_completion", fake_create_completion)

    result = client.generate_chat("hello", model="gemini-3.5-flash-lite")

    assert captured["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert result.usage is not None
    assert result.usage.tokens_out == 25
    assert result.usage.cost == pytest.approx(0.0000655)


def test_openai_passes_messages_as_input(monkeypatch: Any) -> None:
    from clients.openai.client import OpenAIClient

    client = OpenAIClient(api_key="test-key")
    captured: Dict[str, Any] = {}

    def fake_create_response(**kwargs: Any) -> Tuple[Dict[str, Any], float]:
        captured.update(kwargs)
        data = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "BODY"}],
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        return data, 1.0

    monkeypatch.setattr(client, "_create_response", fake_create_response)

    messages = _two_user_messages()
    result = client.generate_chat("ignored", model="gpt-test", messages=messages)

    assert result.response_text == "BODY"
    # OpenAI Responses API accepts consecutive same-role messages as-is.
    assert captured["input"] == messages


def test_unified_forwards_messages_to_cloud_backend(monkeypatch: Any) -> None:
    from clients.anthropic.client import AnthropicClient
    from clients.types import Response
    from clients.unified_client import UnifiedLLMClient

    unified = UnifiedLLMClient(debug=False)
    backend = AnthropicClient(api_key="test-key")
    captured: Dict[str, Any] = {}

    def fake_generate_chat(**kwargs: Any) -> Response:
        captured.update(kwargs)
        return Response(response_text="OK", structured_data={}, usage=None)

    monkeypatch.setattr(backend, "generate_chat", fake_generate_chat)
    monkeypatch.setattr(unified, "_get_client", lambda model: (backend, model, None))
    monkeypatch.setattr(unified, "_get_backend_name", lambda client: "anthropic")

    msgs = _two_user_messages()
    result = unified.generate_chat("", model="claude-test", messages=msgs)

    assert result.response_text == "OK"
    assert captured["messages"] == msgs


def test_unified_rejects_messages_for_local_backend(monkeypatch: Any) -> None:
    from clients.ollama_client import OllamaClient
    from clients.unified_client import UnifiedLLMClient

    unified = UnifiedLLMClient(debug=False)
    backend = OllamaClient()
    monkeypatch.setattr(unified, "_get_client", lambda model: (backend, model, None))
    monkeypatch.setattr(unified, "_get_backend_name", lambda client: "ollama")

    with pytest.raises(NotImplementedError):
        unified.generate_chat("", model="local-test", messages=_two_user_messages())
