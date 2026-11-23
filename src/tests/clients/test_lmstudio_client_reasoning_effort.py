"""Tests for the fixed per-family reasoning effort in the LM Studio client."""

from typing import Any, Dict

import pytest

from clients import lmstudio_client
from clients.lmstudio_client import LMStudioClient, reasoning_effort_for_model


class _FakeElapsed:
    def total_seconds(self) -> float:
        return 0.001


class _FakeChatResponse:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload
        self.elapsed = _FakeElapsed()

    def json(self) -> Dict[str, Any]:
        return self._payload


def _capture_request(monkeypatch: pytest.MonkeyPatch, client: LMStudioClient) -> Dict[str, Any]:
    captured: Dict[str, Any] = {}

    def fake_make_request(endpoint: str, data: Dict[str, Any]) -> _FakeChatResponse:
        captured["data"] = data
        return _FakeChatResponse(
            {"model": data["model"], "choices": [{"message": {"content": "hello"}}]}
        )

    monkeypatch.setattr(client, "_make_request", fake_make_request)
    return captured


def test_reasoning_effort_matches_family_substring_case_insensitively() -> None:
    assert reasoning_effort_for_model("powera/inkling-2-mini-iq2") == "low"
    assert reasoning_effort_for_model("bartowski/thinkingmachines_Inkling-2-Mini-GGUF") == "low"


def test_reasoning_effort_is_none_for_unlisted_models() -> None:
    assert reasoning_effort_for_model("lmstudio-community/Qwen3-4B-GGUF") is None


def test_reasoning_effort_rejects_invalid_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lmstudio_client, "LMSTUDIO_REASONING_EFFORTS", {"inkling-2": "max"})
    with pytest.raises(ValueError, match="Invalid reasoning effort 'max'"):
        reasoning_effort_for_model("powera/inkling-2-mini-iq2")


def test_generate_chat_sends_reasoning_effort_for_listed_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LMStudioClient(timeout=40, debug=False)
    captured = _capture_request(monkeypatch, client)

    client.generate_chat(prompt="hi", model="powera/inkling-2-mini-iq2")

    assert captured["data"]["reasoning_effort"] == "low"


def test_generate_chat_omits_reasoning_effort_for_other_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LMStudioClient(timeout=40, debug=False)
    captured = _capture_request(monkeypatch, client)

    client.generate_chat(prompt="hi", model="lmstudio-community/Qwen3-4B-GGUF")

    assert "reasoning_effort" not in captured["data"]
