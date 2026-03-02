#!/usr/bin/python3

import json

from benchmarks.lib.utils.base_runner import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult


class _FakeSession:
    def close(self):
        return None


class DummyRunner(BenchmarkRunner):
    def __init__(self, model, metadata, scripted_results):
        self._scripted_results = list(scripted_results)
        self.saved = False
        super().__init__(model, metadata)

    def load_questions(self):
        return [
            {"question_id": f"q{i}", "question_info_json": "{}"}
            for i in range(len(self._scripted_results))
        ]

    def warm_up(self):
        return None

    def prepare_prompt(self, question_data):
        return "", None, None

    def process_question(self, question):
        idx = int(question["question_id"][1:])
        return self._scripted_results[idx]

    def save_results(self, score, details):
        self.saved = True
        return 123


def _metadata():
    return BenchmarkMetadata(code="9999_dummy", name="Dummy")


def test_run_skips_db_write_when_no_successful_results(monkeypatch):
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_benchmarks.create_dev_session",
        lambda: _FakeSession(),
    )
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_common.get_model_by_codename",
        lambda session, codename: None,
    )
    unload_calls = []
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.unified_client.unload_model",
        lambda model: unload_calls.append(model),
    )

    results = [
        BenchmarkResult(
            question_id="q0", score=0, eval_msec=0, debug_json=json.dumps({"error": "server error"})
        ),
        BenchmarkResult(
            question_id="q1",
            score=0,
            eval_msec=0,
            debug_json=json.dumps({"error": "request timeout"}),
        ),
    ]
    runner = DummyRunner("test-model", _metadata(), results)

    run_id = runner.run()

    assert run_id == -1
    assert runner.saved is False
    assert unload_calls == [runner.remote_model]


def test_run_aborts_after_more_than_three_server_errors(monkeypatch):
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_benchmarks.create_dev_session",
        lambda: _FakeSession(),
    )
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_common.get_model_by_codename",
        lambda session, codename: None,
    )
    unload_calls = []
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.unified_client.unload_model",
        lambda model: unload_calls.append(model),
    )

    results = [
        BenchmarkResult(
            question_id=f"q{i}",
            score=0,
            eval_msec=0,
            debug_json=json.dumps({"error": "server error 500"}),
        )
        for i in range(5)
    ]
    runner = DummyRunner("test-model", _metadata(), results)

    run_id = runner.run()

    assert run_id == -1
    assert runner.saved is False
    assert unload_calls == [runner.remote_model]


def test_unexpected_response_does_not_count_as_server_error(monkeypatch):
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_benchmarks.create_dev_session",
        lambda: _FakeSession(),
    )
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_common.get_model_by_codename",
        lambda session, codename: None,
    )

    runner = DummyRunner("test-model", _metadata(), [])
    result = BenchmarkResult(
        question_id="q0",
        score=0,
        eval_msec=0,
        debug_json=json.dumps({"error": "Server returned unexpected response format"}),
    )

    assert runner._is_server_error(result) is False
