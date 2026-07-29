class _DummyBackendClient:
    def __init__(self, *args, **kwargs):
        self.debug = False


class _DummySession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_local_model_resolution_is_cached_and_closes_session(monkeypatch):
    monkeypatch.setattr("clients.unified_client.openai_client.OpenAIClient", _DummyBackendClient)
    monkeypatch.setattr(
        "clients.unified_client.anthropic_client.AnthropicClient", _DummyBackendClient
    )
    monkeypatch.setattr("clients.unified_client.gemini_client.GeminiClient", _DummyBackendClient)
    monkeypatch.setattr("clients.unified_client.ollama_client.OllamaClient", _DummyBackendClient)
    monkeypatch.setattr(
        "clients.unified_client.lmstudio_client.LMStudioClient", _DummyBackendClient
    )

    from clients.unified_client import UnifiedLLMClient

    client = UnifiedLLMClient(debug=False)
    monkeypatch.setattr(client, "_get_backend_name", lambda _client: "lmstudio")

    create_calls = []
    lookup_calls = []
    created_sessions = []

    def fake_create_dev_session():
        create_calls.append(1)
        session = _DummySession()
        created_sessions.append(session)
        return session

    def fake_get_model_by_codename(session, codename):
        lookup_calls.append((session, codename))
        return {
            "model_path": "lmstudio/lmstudio-community/Qwen3-4B-GGUF",
            "lmstudio_model_name": "qwen3-4b",
            "model_type": "local",
        }

    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.create_dev_session",
        fake_create_dev_session,
    )
    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.get_model_by_codename",
        fake_get_model_by_codename,
    )

    first_client, first_model, first_expected = client._get_client("qwen3-4b-lms")
    second_client, second_model, second_expected = client._get_client("qwen3-4b-lms")

    assert first_model == "lmstudio-community/Qwen3-4B-GGUF"
    assert second_model == "lmstudio-community/Qwen3-4B-GGUF"
    assert first_expected == "qwen3-4b"
    assert second_expected == "qwen3-4b"

    assert len(create_calls) == 1
    assert len(lookup_calls) == 1

    assert len(created_sessions) == 1
    assert created_sessions[0].closed is True


def _patch_all_backends(monkeypatch, digitalocean=_DummyBackendClient):
    """Replace every backend constructor so no client touches a key file or network."""
    monkeypatch.setattr("clients.unified_client.openai_client.OpenAIClient", _DummyBackendClient)
    monkeypatch.setattr(
        "clients.unified_client.anthropic_client.AnthropicClient", _DummyBackendClient
    )
    monkeypatch.setattr("clients.unified_client.gemini_client.GeminiClient", _DummyBackendClient)
    monkeypatch.setattr("clients.unified_client.ollama_client.OllamaClient", _DummyBackendClient)
    monkeypatch.setattr(
        "clients.unified_client.lmstudio_client.LMStudioClient", _DummyBackendClient
    )
    monkeypatch.setattr(
        "clients.unified_client.digitalocean_client.DigitalOceanClient", digitalocean
    )


def _explode_on_db(*args, **kwargs):
    raise AssertionError("do/ routing must not hit the model database")


def test_do_prefix_routes_to_digitalocean_and_strips_prefix(monkeypatch):
    """A do/ model goes to the DigitalOcean backend with the prefix stripped."""
    _patch_all_backends(monkeypatch)
    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.create_dev_session", _explode_on_db
    )

    from clients.unified_client import UnifiedLLMClient

    client = UnifiedLLMClient(debug=False)

    resolved, normalized, expected = client._get_client("do/anthropic-claude-fable-5")

    assert resolved is client.digitalocean
    assert normalized == "anthropic-claude-fable-5"
    assert expected is None


def test_do_prefix_resolution_is_cached(monkeypatch):
    """The second lookup comes from the cache fast path, not the branch chain."""
    _patch_all_backends(monkeypatch)
    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.create_dev_session", _explode_on_db
    )

    from clients.unified_client import UnifiedLLMClient

    client = UnifiedLLMClient(debug=False)

    client._get_client("do/openai-gpt-5.6-sol")
    assert client._model_resolution_cache["do/openai-gpt-5.6-sol"] == (
        "digitalocean",
        "openai-gpt-5.6-sol",
        None,
    )

    cached_client, cached_model, cached_expected = client._get_client("do/openai-gpt-5.6-sol")
    assert cached_client is client.digitalocean
    assert cached_model == "openai-gpt-5.6-sol"
    assert cached_expected is None


def test_do_prefix_wins_over_first_party_prefixes(monkeypatch):
    """do/ is checked first, so an embedded vendor name does not shadow it."""
    _patch_all_backends(monkeypatch)
    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.create_dev_session", _explode_on_db
    )

    from clients.unified_client import UnifiedLLMClient

    client = UnifiedLLMClient(debug=False)

    for model_name in ("do/openai-gpt-5.6-sol", "do/anthropic-claude-fable-5", "do/gemini-x"):
        resolved, _normalized, _expected = client._get_client(model_name)
        assert resolved is client.digitalocean, model_name

    # A bare first-party name still routes first-party.
    assert client._get_client("gpt-5.4-mini")[0] is client.openai


def test_generate_chat_forwards_messages_and_max_tokens_to_digitalocean(monkeypatch):
    """DigitalOcean is a cloud backend, so messages= and max_tokens= are not dropped."""

    class _CapturingDOClient(_DummyBackendClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.captured_kwargs = None

        def generate_chat(self, **kwargs):
            self.captured_kwargs = kwargs
            from clients.types import Response

            return Response(
                response_text="ok", structured_data={}, usage=None, additional_thought=None
            )

    _patch_all_backends(monkeypatch, digitalocean=_CapturingDOClient)
    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.create_dev_session", _explode_on_db
    )

    from clients.unified_client import UnifiedLLMClient

    client = UnifiedLLMClient(debug=False)
    conversation = [{"role": "user", "content": "hello"}]

    response = client.generate_chat(
        prompt="ignored",
        model="do/llama-4-maverick",
        messages=conversation,
        max_tokens=1234,
    )

    assert response.response_text == "ok"
    assert isinstance(client.digitalocean, _CapturingDOClient)
    captured = client.digitalocean.captured_kwargs
    assert captured is not None
    assert captured["model"] == "llama-4-maverick"
    assert captured["messages"] == conversation
    assert captured["max_tokens"] == 1234


def test_generate_chat_passes_expected_response_model_to_lmstudio(monkeypatch):
    class _CapturingLMStudioClient(_DummyBackendClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.captured_kwargs = None

        def generate_chat(self, **kwargs):
            self.captured_kwargs = kwargs
            from clients.types import Response

            return Response(
                response_text="ok", structured_data={}, usage=None, additional_thought=None
            )

    monkeypatch.setattr("clients.unified_client.openai_client.OpenAIClient", _DummyBackendClient)
    monkeypatch.setattr(
        "clients.unified_client.anthropic_client.AnthropicClient", _DummyBackendClient
    )
    monkeypatch.setattr("clients.unified_client.gemini_client.GeminiClient", _DummyBackendClient)
    monkeypatch.setattr("clients.unified_client.ollama_client.OllamaClient", _DummyBackendClient)
    monkeypatch.setattr(
        "clients.unified_client.lmstudio_client.LMStudioClient", _CapturingLMStudioClient
    )

    from clients.unified_client import UnifiedLLMClient

    client = UnifiedLLMClient(debug=False)

    class _DummySessionForModel:
        def close(self):
            return None

    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.create_dev_session",
        lambda: _DummySessionForModel(),
    )
    monkeypatch.setattr(
        "clients.unified_client.benchmarks.datastore.common.get_model_by_codename",
        lambda session, codename: {
            "model_path": "lmstudio/TheBloke/Llama-2-7B-GGUF",
            "lmstudio_model_name": "llama-2-7b",
            "model_type": "local",
        },
    )

    response = client.generate_chat(prompt="hello", model="llama-2-7b-lms")

    assert response.response_text == "ok"
    assert isinstance(client.lmstudio, _CapturingLMStudioClient)
    assert client.lmstudio.captured_kwargs is not None
    assert client.lmstudio.captured_kwargs["model"] == "TheBloke/Llama-2-7B-GGUF"
    assert client.lmstudio.captured_kwargs["expected_response_model"] == "llama-2-7b"
