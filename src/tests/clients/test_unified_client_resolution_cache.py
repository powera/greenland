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
