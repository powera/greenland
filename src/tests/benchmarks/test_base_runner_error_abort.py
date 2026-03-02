import json
import sys
import types

if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")
    setattr(pydantic_stub, "BaseModel", object)
    sys.modules["pydantic"] = pydantic_stub

from benchmarks.lib.utils.base_runner import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult


class _DummyRunner(BenchmarkRunner):
    def prepare_prompt(self, question_data):
        return "prompt", None, None


def test_run_aborts_after_three_errors(monkeypatch):
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_benchmarks.create_dev_session",
        lambda: object(),
    )
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_common.get_model_by_codename",
        lambda session, model: None,
    )

    runner = _DummyRunner("llama-2-7b", BenchmarkMetadata(code="0013", name="test"))

    questions = [
        {"question_id": f"q{i}", "question_info_json": json.dumps({"correct_answer": "x"})}
        for i in range(1, 6)
    ]
    monkeypatch.setattr(runner, "load_questions", lambda: questions)
    monkeypatch.setattr(runner, "warm_up", lambda: None)

    processed_question_ids = []

    def fake_process(question):
        processed_question_ids.append(question["question_id"])
        return BenchmarkResult(
            question_id=question["question_id"],
            score=0,
            eval_msec=0,
            debug_json=json.dumps({"error": "Request timeout"}),
        )

    monkeypatch.setattr(runner, "process_question", fake_process)

    unload_calls = []
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.unified_client.unload_model",
        lambda model: unload_calls.append(model),
    )

    run_id = runner._run_inner()

    assert run_id == -1
    assert processed_question_ids == ["q1", "q2", "q3"]
    assert unload_calls == [runner.remote_model]


def test_run_keeps_lmstudio_model_loaded_after_success(monkeypatch):
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_benchmarks.create_dev_session",
        lambda: object(),
    )
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.datastore_common.get_model_by_codename",
        lambda session, model: {"model_path": "lmstudio/lmstudio-community/qwen"},
    )

    runner = _DummyRunner("qwen-local", BenchmarkMetadata(code="0013", name="test"))

    questions = [{"question_id": "q1", "question_info_json": json.dumps({"correct_answer": "x"})}]
    monkeypatch.setattr(runner, "load_questions", lambda: questions)
    monkeypatch.setattr(runner, "warm_up", lambda: None)

    monkeypatch.setattr(
        runner,
        "process_question",
        lambda question: BenchmarkResult(
            question_id=question["question_id"], score=100, eval_msec=1
        ),
    )
    monkeypatch.setattr(runner, "save_results", lambda score, details: 42)

    unload_calls = []
    monkeypatch.setattr(
        "benchmarks.lib.utils.base_runner.unified_client.unload_model",
        lambda model: unload_calls.append(model),
    )

    run_id = runner._run_inner()

    assert run_id == 42
    assert unload_calls == []
