from typing import Any, Dict, List

import requests

from clients.lmstudio_client import LMStudioClient, LMStudioModelMismatchError


class _FakeResponse:
    def __init__(self, status_code: int, text: str, payload: Dict[str, Any]):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeElapsed:
    def total_seconds(self) -> float:
        return 0.001


class _FakeChatResponse:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload
        self.elapsed = _FakeElapsed()

    def json(self) -> Dict[str, Any]:
        return self._payload


def test_warm_model_timeout_recovers_from_loaded_state(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)
    post_calls: List[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_calls.append({"url": url, "json": json, "timeout": timeout})
        raise requests.exceptions.ReadTimeout("timeout")

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        return _FakeResponse(
            200,
            "ok",
            {"data": [{"id": "lmstudio-community/qwen"}]},
        )

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("lmstudio-community/qwen") is True
    assert len(post_calls) == 1


def test_unload_model_sends_model_and_instance_id(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)
    payloads: List[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        payloads.append(json)
        return _FakeResponse(409, "Model not loaded", {"error": "not loaded"})

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.unload_model("lmstudio-community/qwen") is True
    assert payloads == [
        {
            "instance_id": "lmstudio-community/qwen",
            "model": "lmstudio-community/qwen",
        }
    ]


def test_warm_model_retries_and_returns_false(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)
    post_attempts: List[int] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_attempts.append(1)
        raise requests.exceptions.ConnectTimeout("timeout")

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, "ok", {"data": [{"id": "some/other-model"}]})

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("lmstudio-community/qwen") is False
    assert len(post_attempts) == 3


def test_generate_chat_sends_requested_model(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)
    captured_request: Dict[str, Any] = {}

    def fake_make_request(endpoint: str, data: Dict[str, Any]) -> _FakeChatResponse:
        captured_request["endpoint"] = endpoint
        captured_request["data"] = data
        return _FakeChatResponse(
            {
                "model": data["model"],
                "choices": [{"message": {"content": "hello"}}],
            }
        )

    monkeypatch.setattr(client, "_make_request", fake_make_request)

    response = client.generate_chat(prompt="hi", model="lmstudio-community/Qwen3-4B-GGUF")

    assert captured_request["endpoint"] == "chat/completions"
    assert captured_request["data"]["model"] == "lmstudio-community/Qwen3-4B-GGUF"
    assert response.response_text == "hello"


def test_generate_chat_accepts_response_model_alias(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)

    def fake_make_request(endpoint: str, data: Dict[str, Any]) -> _FakeChatResponse:
        return _FakeChatResponse(
            {
                "model": "llama-2-7b",
                "choices": [{"message": {"content": "alias works"}}],
            }
        )

    monkeypatch.setattr(client, "_make_request", fake_make_request)

    response = client.generate_chat(prompt="hi", model="TheBloke/Llama-2-7B-GGUF")

    assert response.response_text == "alias works"


def test_generate_chat_raises_on_response_model_mismatch(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)

    def fake_make_request(endpoint: str, data: Dict[str, Any]) -> _FakeChatResponse:
        return _FakeChatResponse(
            {
                "model": "lmstudio-community/Llama-2-7B-GGUF",
                "choices": [{"message": {"content": "wrong model"}}],
            }
        )

    monkeypatch.setattr(client, "_make_request", fake_make_request)

    try:
        client.generate_chat(prompt="hi", model="lmstudio-community/Llama-3-8B-GGUF")
        assert False, "Expected LMStudioModelMismatchError"
    except LMStudioModelMismatchError as model_error:
        assert "requested 'lmstudio-community/Llama-3-8B-GGUF'" in str(model_error)
