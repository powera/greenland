from types import SimpleNamespace

from flask import Flask, g

from benchmarks.server.routes import verbalator


class _FakeQuery:
    def __init__(self, model):
        self._model = model

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._model


class _FakeDB:
    def __init__(self, model):
        self._model = model

    def query(self, *_args, **_kwargs):
        return _FakeQuery(self._model)


class _FakeWorker:
    def __init__(self, allow_local_query):
        self.allow_local_query = allow_local_query

    def touch_interactive_local_job(self, **_kwargs):
        return self.allow_local_query


def test_can_start_local_query_uses_worker_slot():
    app = Flask(__name__)

    with app.app_context():
        app.extensions["benchmark_run_worker"] = _FakeWorker(allow_local_query=True)
        assert verbalator._can_start_local_query("llama3") is True

        app.extensions["benchmark_run_worker"] = _FakeWorker(allow_local_query=False)
        assert verbalator._can_start_local_query("llama3") is False


def test_query_blocks_local_model_when_worker_denies_slot(monkeypatch):
    app = Flask(__name__)
    app.extensions["benchmark_run_worker"] = _FakeWorker(allow_local_query=False)

    local_model = SimpleNamespace(model_type="ollama", model_path="llama3", codename="local")

    monkeypatch.setattr(verbalator.prompt_builder, "build", lambda *_args, **_kwargs: "Prompt")

    class _NeverCalledClient:
        def generate_chat(self, *_args, **_kwargs):
            raise AssertionError("Local request should be blocked before model generation")

    monkeypatch.setattr(verbalator, "_get_unified_client", lambda: _NeverCalledClient())

    with app.test_request_context(
        "/verbalator/query",
        method="POST",
        json={"prompt": "basic", "entry": "hello", "model": "local"},
    ):
        g.db = _FakeDB(local_model)
        response, status = verbalator.query()

    assert status == 409
    assert "busy" in response.get_json()["error"].lower()
