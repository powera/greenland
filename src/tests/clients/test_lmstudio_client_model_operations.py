from typing import Any, Dict, List

import requests

from clients.lmstudio_client import LMStudioClient, LMStudioModelMismatchError

# Real /api/v0/models response shapes.
# Each entry has "id" and "state"; state is one of:
#   "loading", "not-loaded", "loaded", "idle"
# The id is the short key (e.g. "qwen3-4b"), not "publisher/key".
# Callers pass publisher/key (e.g. "lmstudio-community/qwen3-4b"), so matching
# must handle both bare id and publisher/id.

_QWEN_LOADED = {
    "data": [
        {"id": "qwen3-4b", "state": "loaded"},
        {"id": "meta-llama-3.1-8b-instruct", "state": "not-loaded"},
    ]
}

_QWEN_NOT_LOADED = {
    "data": [
        {"id": "qwen3-4b", "state": "not-loaded"},
        {"id": "meta-llama-3.1-8b-instruct", "state": "not-loaded"},
    ]
}

_QWEN_LOADING = {
    "data": [
        {"id": "qwen3-4b", "state": "loading"},
        {"id": "meta-llama-3.1-8b-instruct", "state": "not-loaded"},
    ]
}

_OTHER_MODEL_LOADED = {
    "data": [
        {"id": "qwen3-4b", "state": "not-loaded"},
        {"id": "meta-llama-3.1-8b-instruct", "state": "loaded"},
    ]
}

# Gemma: caller passes "google/gemma-2-2b-it"; id in API is "gemma-2-2b-it".
_GEMMA_LOADED = {
    "data": [
        {"id": "gemma-2-2b-it", "state": "loaded"},
    ]
}

_GEMMA_NOT_LOADED = {
    "data": [
        {"id": "gemma-2-2b-it", "state": "not-loaded"},
    ]
}

_NOTHING_LOADED: Dict[str, Any] = {
    "data": [
        {"id": "qwen3-4b", "state": "not-loaded"},
    ]
}


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


def test_warm_model_skips_load_when_already_ready(monkeypatch):
    """If the target model is already loaded and ready, warm_model returns True with no POST."""
    client = LMStudioClient(timeout=40, debug=False)
    post_calls: List[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_calls.append({"url": url, "json": json, "timeout": timeout})
        raise requests.exceptions.ReadTimeout("timeout")

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, "ok", _QWEN_LOADED)

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("qwen3-4b") is True
    # Model is already ready — no load POST should be sent at all.
    assert len(post_calls) == 0


def test_warm_model_skips_load_when_idle(monkeypatch):
    """State "idle" is also considered ready — warm_model returns True immediately."""
    client = LMStudioClient(timeout=40, debug=False)
    post_calls: List[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse(200, "ok", {})

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, "ok", {"data": [{"id": "qwen3-4b", "state": "idle"}]})

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("qwen3-4b") is True
    assert len(post_calls) == 0


def test_warm_model_unloads_other_models_first(monkeypatch):
    """When another model is loaded, warm_model unloads it before loading the target."""
    client = LMStudioClient(timeout=40, debug=False)
    post_urls: List[str] = []
    post_payloads: List[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_urls.append(url)
        post_payloads.append(json)
        return _FakeResponse(200, "ok", {})

    get_calls: List[int] = []

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        get_calls.append(1)
        # First GET: fast-path check — qwen not loaded, llama is loaded.
        # Second GET: _get_loaded_model_ids — same.
        # Third+ GETs: poll until qwen loaded.
        if len(get_calls) <= 2:
            return _FakeResponse(200, "ok", _OTHER_MODEL_LOADED)
        return _FakeResponse(200, "ok", _QWEN_LOADED)

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("qwen3-4b") is True
    unload_urls = [u for u in post_urls if "unload" in u]
    load_urls = [u for u in post_urls if "load" in u and "unload" not in u]
    assert len(unload_urls) == 1
    assert post_payloads[0].get("instance_id") == "meta-llama-3.1-8b-instruct"
    assert len(load_urls) == 1


def test_warm_model_does_not_unload_not_loaded_models(monkeypatch):
    """Models in state "not-loaded" must not be unloaded."""
    client = LMStudioClient(timeout=40, debug=False)
    post_urls: List[str] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_urls.append(url)
        return _FakeResponse(200, "ok", {})

    get_calls: List[int] = []

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        get_calls.append(1)
        if len(get_calls) <= 2:
            return _FakeResponse(200, "ok", _NOTHING_LOADED)
        return _FakeResponse(200, "ok", _QWEN_LOADED)

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("qwen3-4b") is True
    unload_urls = [u for u in post_urls if "unload" in u]
    load_urls = [u for u in post_urls if "load" in u and "unload" not in u]
    assert len(unload_urls) == 0
    assert len(load_urls) == 1


def test_unload_model_sends_only_instance_id(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)
    payloads: List[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        payloads.append(json)
        return _FakeResponse(409, "Model not loaded", {"error": "not loaded"})

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.unload_model("qwen3-4b") is True
    assert payloads == [{"instance_id": "qwen3-4b"}]


def test_warm_model_matches_publisher_slash_key(monkeypatch):
    """Caller passes publisher/key (e.g. google/gemma-2-2b-it); API id is bare (gemma-2-2b-it)."""
    client = LMStudioClient(timeout=40, debug=False)
    post_calls: List[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_calls.append(json)
        return _FakeResponse(200, "ok", {})

    get_calls: List[int] = []

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        get_calls.append(1)
        # First GET: fast-path — not loaded yet.
        # Second GET: _get_loaded_model_ids — nothing else to unload.
        # Third+ GETs: poll until loaded.
        if len(get_calls) <= 2:
            return _FakeResponse(200, "ok", _GEMMA_NOT_LOADED)
        return _FakeResponse(200, "ok", _GEMMA_LOADED)

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    # Caller uses the publisher/key form as stored in model_path.
    assert client.warm_model("google/gemma-2-2b-it") is True
    load_calls = [c for c in post_calls if "unload" not in str(c)]
    assert len(load_calls) == 1


def test_warm_model_polls_while_loading(monkeypatch):
    """Load POST succeeds; polling via GET while state is "loading" until "loaded"."""
    client = LMStudioClient(timeout=40, debug=False)
    post_attempts: List[int] = []
    get_calls: List[int] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_attempts.append(1)
        return _FakeResponse(200, "ok", {})

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        get_calls.append(1)
        # First: not-loaded (fast path). Second: not-loaded (get_loaded_ids).
        # Third and fourth: loading state. Fifth+: loaded.
        if len(get_calls) <= 2:
            return _FakeResponse(200, "ok", _QWEN_NOT_LOADED)
        if len(get_calls) <= 4:
            return _FakeResponse(200, "ok", _QWEN_LOADING)
        return _FakeResponse(200, "ok", _QWEN_LOADED)

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("qwen3-4b") is True
    # Only one load POST; polling continues until loaded.
    assert len(post_attempts) == 1
    assert len(get_calls) >= 5


def test_warm_model_retries_load_when_state_is_not_loaded(monkeypatch):
    """If state drops to "not-loaded" during polling, a retry load POST is sent."""
    client = LMStudioClient(timeout=40, debug=False)
    post_calls: List[str] = []
    get_calls: List[int] = []

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        post_calls.append(url)
        return _FakeResponse(200, "ok", {})

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        get_calls.append(1)
        # First two GETs: not-loaded (fast path + get_loaded_ids).
        # Third GET (first poll): not-loaded again — triggers retry load POST.
        # Fourth GET: loaded.
        if len(get_calls) <= 3:
            return _FakeResponse(200, "ok", _QWEN_NOT_LOADED)
        return _FakeResponse(200, "ok", _QWEN_LOADED)

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)

    assert client.warm_model("qwen3-4b") is True
    load_urls = [u for u in post_calls if "load" in u and "unload" not in u]
    # First load POST + one retry load POST when state was "not-loaded" during polling.
    assert len(load_urls) == 2


def test_warm_model_returns_false_when_model_never_appears(monkeypatch):
    """When the model never becomes ready before timeout, warm_model returns False."""
    client = LMStudioClient(timeout=40, debug=False)

    def fake_post(url: str, json: Dict[str, Any], timeout: float) -> _FakeResponse:
        return _FakeResponse(200, "ok", {})

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, "ok", _QWEN_NOT_LOADED)

    call_count = [0]
    original_time = __import__("time").time

    def fake_time() -> float:
        call_count[0] += 1
        # After enough calls, simulate timeout by returning a large value.
        if call_count[0] > 10:
            return original_time() + 1000
        return original_time()

    monkeypatch.setattr("clients.lmstudio_client.requests.post", fake_post)
    monkeypatch.setattr("clients.lmstudio_client.requests.get", fake_get)
    monkeypatch.setattr("clients.lmstudio_client.time.sleep", lambda *_: None)
    monkeypatch.setattr("clients.lmstudio_client.time.time", fake_time)

    assert client.warm_model("qwen3-4b") is False


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


def test_generate_chat_accepts_expected_response_model_name(monkeypatch):
    client = LMStudioClient(timeout=40, debug=False)

    def fake_make_request(endpoint: str, data: Dict[str, Any]) -> _FakeChatResponse:
        return _FakeChatResponse(
            {
                "model": "llama-2-7b",
                "choices": [{"message": {"content": "alias works"}}],
            }
        )

    monkeypatch.setattr(client, "_make_request", fake_make_request)

    response = client.generate_chat(
        prompt="hi",
        model="TheBloke/Llama-2-7B-GGUF",
        expected_response_model="llama-2-7b",
    )

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
