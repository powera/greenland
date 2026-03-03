#!/usr/bin/python3
"""Tests for missing benchmark scheduling and session handling."""

import sys
import types

if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:  # pragma: no cover - compatibility shim
        pass

    setattr(pydantic_stub, "BaseModel", BaseModel)
    sys.modules["pydantic"] = pydantic_stub

from benchmarks import run_benchmark


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_get_all_model_codenames_prioritizes_local_and_closes_session(monkeypatch) -> None:
    fake_session = _FakeSession()

    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "create_dev_session",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "list_all_models",
        lambda _session: [
            {"codename": "remote-z", "displayname": "Zeta", "model_type": "remote"},
            {"codename": "local-b", "displayname": "Beta", "model_type": "local"},
            {"codename": "local-a", "displayname": "Alpha", "model_type": "local"},
        ],
    )

    ordered = run_benchmark.get_all_model_codenames(prioritize_local=True)

    assert ordered == ["local-a", "local-b", "remote-z"]
    assert fake_session.closed is True


def test_run_missing_benchmarks_groups_by_model_and_closes_owned_session(monkeypatch) -> None:
    fake_session = _FakeSession()
    run_calls = []

    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "create_dev_session",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        run_benchmark,
        "get_all_model_codenames",
        lambda prioritize_local=False: ["local-model", "remote-model"],
    )
    monkeypatch.setattr(
        run_benchmark,
        "get_enabled_benchmark_codes",
        lambda: ["001_first", "002_second"],
    )
    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "list_all_models",
        lambda _session: [
            {"codename": "local-model", "max_benchmark_tier": 1},
            {"codename": "remote-model", "max_benchmark_tier": 2},
        ],
    )
    monkeypatch.setattr(
        run_benchmark.datastore_benchmarks,
        "get_highest_benchmark_scores",
        lambda _session: set(),
    )

    def fake_run(benchmark_code: str, model_name: str) -> int:
        run_calls.append((model_name, benchmark_code))
        return 123

    monkeypatch.setattr(run_benchmark, "run_benchmark", fake_run)

    run_pairs = run_benchmark.run_missing_benchmarks()

    assert run_calls == [
        ("local-model", "001_first"),
        ("local-model", "002_second"),
        ("remote-model", "001_first"),
        ("remote-model", "002_second"),
    ]
    assert run_pairs == run_calls
    assert fake_session.closed is True


def test_run_missing_benchmarks_filters_by_tier(monkeypatch) -> None:
    fake_session = _FakeSession()
    run_calls = []

    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "create_dev_session",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        run_benchmark,
        "get_all_model_codenames",
        lambda prioritize_local=False: ["local-model"],
    )
    monkeypatch.setattr(
        run_benchmark,
        "get_enabled_benchmark_codes",
        lambda: ["0031_definitions", "0062_sentence_decomposition"],
    )
    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "list_all_models",
        lambda _session: [{"codename": "local-model", "max_benchmark_tier": 3}],
    )
    monkeypatch.setattr(
        run_benchmark.datastore_benchmarks,
        "get_highest_benchmark_scores",
        lambda _session: set(),
    )

    def fake_run(benchmark_code: str, model_name: str) -> int:
        run_calls.append((model_name, benchmark_code))
        return 456

    monkeypatch.setattr(run_benchmark, "run_benchmark", fake_run)

    run_pairs = run_benchmark.run_missing_benchmarks(tier=3)

    assert run_calls == [("local-model", "0062_sentence_decomposition")]
    assert run_pairs == run_calls


def test_run_missing_benchmarks_applies_capability_tier_rules(monkeypatch) -> None:
    fake_session = _FakeSession()
    run_calls = []

    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "create_dev_session",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        run_benchmark,
        "get_all_model_codenames",
        lambda prioritize_local=False: ["cap1", "cap2", "cap3"],
    )
    monkeypatch.setattr(
        run_benchmark,
        "get_enabled_benchmark_codes",
        lambda: [
            "0016_antonym",  # tier 1
            "0031_definitions",  # tier 2
            "0062_sentence_decomposition",  # tier 3
        ],
    )
    monkeypatch.setattr(
        run_benchmark.datastore_common,
        "list_all_models",
        lambda _session: [
            {"codename": "cap1", "max_benchmark_tier": 1},
            {"codename": "cap2", "max_benchmark_tier": 2},
            {"codename": "cap3", "max_benchmark_tier": 3},
        ],
    )
    monkeypatch.setattr(
        run_benchmark.datastore_benchmarks,
        "get_highest_benchmark_scores",
        lambda _session: set(),
    )

    def fake_run(benchmark_code: str, model_name: str) -> int:
        run_calls.append((model_name, benchmark_code))
        return 999

    monkeypatch.setattr(run_benchmark, "run_benchmark", fake_run)

    run_pairs = run_benchmark.run_missing_benchmarks()

    assert ("cap1", "0016_antonym") in run_calls
    assert ("cap1", "0031_definitions") in run_calls
    assert ("cap1", "0062_sentence_decomposition") not in run_calls

    assert ("cap2", "0016_antonym") in run_calls
    assert ("cap2", "0031_definitions") in run_calls
    assert ("cap2", "0062_sentence_decomposition") in run_calls

    assert ("cap3", "0016_antonym") in run_calls
    assert ("cap3", "0031_definitions") in run_calls
    assert ("cap3", "0062_sentence_decomposition") in run_calls

    assert run_pairs == run_calls


def test_missing_cli_rejects_tier_with_blacklist(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        run_benchmark.sys,
        "argv",
        [
            "run_benchmark.py",
            "missing",
            "--tier",
            "1",
            "--blacklist-benchmarks",
            "0016_antonym",
        ],
    )

    try:
        run_benchmark.main()
        assert (
            False
        ), "Expected argparse to exit when --tier and --blacklist-benchmarks are combined"
    except SystemExit as exc:
        assert exc.code == 2

    stderr = capsys.readouterr().err
    assert "--tier cannot be used together with --blacklist-benchmarks" in stderr
