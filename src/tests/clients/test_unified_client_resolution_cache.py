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
    monkeypatch.setattr("clients.unified_client.anthropic_client.AnthropicClient", _DummyBackendClient)
    monkeypatch.setattr("clients.unified_client.gemini_client.GeminiClient", _DummyBackendClient)
    monkeypatch.setattr("clients.unified_client.ollama_client.OllamaClient", _DummyBackendClient)
    monkeypatch.setattr("clients.unified_client.lmstudio_client.LMStudioClient", _DummyBackendClient)

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

    first_client, first_model = client._get_client("qwen3-4b-lms")
    second_client, second_model = client._get_client("qwen3-4b-lms")

    assert first_model == "lmstudio-community/Qwen3-4B-GGUF"
    assert second_model == "lmstudio-community/Qwen3-4B-GGUF"

    assert len(create_calls) == 1
    assert len(lookup_calls) == 1

    assert len(created_sessions) == 1
    assert created_sessions[0].closed is True
