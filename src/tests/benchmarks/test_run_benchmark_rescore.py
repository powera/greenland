#!/usr/bin/python3
"""Tests for benchmark rescoring CLI helpers."""

import json

from benchmarks import run_benchmark
from benchmarks.datastore import benchmarks as datastore_benchmarks
from benchmarks.datastore import common as datastore_common


class FakeRunner:
    def score_response(self, question_data, response):
        expected = question_data["correct_answer"]
        return 100 if response == expected else 40


def test_rescore_benchmark_runs_updates_scores_and_normed_score(tmp_path, monkeypatch):
    db_path = tmp_path / "benchmarks.sqlite"
    session = datastore_common.create_database_and_session(db_path)

    datastore_common.insert_model(session, codename="m1", displayname="Model 1")
    datastore_benchmarks.insert_benchmark(session, codename="0062_sentence_decomposition", displayname="SD")

    datastore_benchmarks.insert_question(
        session,
        question_id="q1",
        benchmark_name="0062_sentence_decomposition",
        question_info_json=json.dumps({"correct_answer": {"ok": 1}}),
    )
    datastore_benchmarks.insert_question(
        session,
        question_id="q2",
        benchmark_name="0062_sentence_decomposition",
        question_info_json=json.dumps({"correct_answer": {"ok": 2}}),
    )

    ok, run_id = datastore_benchmarks.insert_run(
        session,
        model_name="m1",
        benchmark_name="0062_sentence_decomposition",
        normed_score=0,
        run_details=[
            {
                "question_id": "q1",
                "score": 0,
                "debug_json": json.dumps({"response": {"ok": 1}}),
            },
            {
                "question_id": "q2",
                "score": 0,
                "debug_json": json.dumps({"response": {"bad": 2}}),
            },
        ],
    )
    assert ok

    monkeypatch.setattr(run_benchmark, "get_runner", lambda benchmark, model: FakeRunner())

    summary = run_benchmark.rescore_benchmark_runs(
        benchmark_code="0062_sentence_decomposition",
        session=session,
    )

    assert summary == {
        "runs_considered": 1,
        "runs_updated": 1,
        "details_rescored": 2,
        "details_skipped": 0,
    }

    run = session.query(datastore_benchmarks.Run).filter(datastore_benchmarks.Run.run_id == run_id).one()
    details = (
        session.query(datastore_benchmarks.RunDetail)
        .filter(datastore_benchmarks.RunDetail.run_id == run_id)
        .order_by(datastore_benchmarks.RunDetail.question_id.asc())
        .all()
    )

    assert details[0].score == 100
    assert details[1].score == 40
    assert run.normed_score == 70


def test_rescore_benchmark_runs_can_filter_model(tmp_path, monkeypatch):
    db_path = tmp_path / "benchmarks.sqlite"
    session = datastore_common.create_database_and_session(db_path)

    datastore_common.insert_model(session, codename="m1", displayname="Model 1")
    datastore_common.insert_model(session, codename="m2", displayname="Model 2")
    datastore_benchmarks.insert_benchmark(session, codename="0062_sentence_decomposition", displayname="SD")

    for qid in ["q1", "q2"]:
        datastore_benchmarks.insert_question(
            session,
            question_id=qid,
            benchmark_name="0062_sentence_decomposition",
            question_info_json=json.dumps({"correct_answer": {"k": qid}}),
        )

    datastore_benchmarks.insert_run(
        session,
        model_name="m1",
        benchmark_name="0062_sentence_decomposition",
        normed_score=0,
        run_details=[{"question_id": "q1", "score": 0, "debug_json": json.dumps({"response": {"k": "q1"}})}],
    )
    datastore_benchmarks.insert_run(
        session,
        model_name="m2",
        benchmark_name="0062_sentence_decomposition",
        normed_score=0,
        run_details=[{"question_id": "q2", "score": 0, "debug_json": json.dumps({"response": {"k": "q2"}})}],
    )

    monkeypatch.setattr(run_benchmark, "get_runner", lambda benchmark, model: FakeRunner())

    summary = run_benchmark.rescore_benchmark_runs(
        benchmark_code="0062_sentence_decomposition",
        model="m2",
        session=session,
    )

    assert summary["runs_considered"] == 1
    assert summary["details_rescored"] == 1
