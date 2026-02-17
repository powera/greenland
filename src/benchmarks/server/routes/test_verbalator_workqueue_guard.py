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
    def __init__(self, status_payload):
        self._status_payload = status_payload

    def status(self):
        return self._status_payload


def test_is_benchmark_worker_busy_states():
    app = Flask(__name__)

    with app.app_context():
        app.extensions["benchmark_run_worker"] = _FakeWorker({"active": None, "queued": 0})
        assert verbalator._is_benchmark_worker_busy() is False

        app.extensions["benchmark_run_worker"] = _FakeWorker({"active": {"task_id": 1}, "queued": 0})
        assert verbalator._is_benchmark_worker_busy() is True

        app.extensions["benchmark_run_worker"] = _FakeWorker({"active": None, "queued": 2})
        assert verbalator._is_benchmark_worker_busy() is True


def test_query_blocks_local_model_when_workqueue_busy(monkeypatch):
    app = Flask(__name__)
    app.extensions["benchmark_run_worker"] = _FakeWorker({"active": {"task_id": 7}, "queued": 0})

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
    assert "blocked" in response.get_json()["error"].lower()
