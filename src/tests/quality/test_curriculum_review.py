"""Safety and offline batch tests for sense-specific curriculum reviews."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from quality import curriculum_review as review
from quality.level_placement import MenuLevel
from reports.level_candidates import PlacementQuery, query_for_lemma
from reports.curriculum_bands import apply_moves
from storage.models.schema import Base, Lemma


def query(tier: str | None) -> PlacementQuery:
    return PlacementQuery(
        lemma_text="vector",
        pos_type="noun",
        definition="disease carrier",
        pos_subtype=None,
        rank=None,
        tiers=(("cefr", tier),) if tier else (),
    )


@pytest.mark.parametrize(
    "tier,cefr_pass,exception,core",
    [
        ("B1", False, False, False),
        ("B1", True, False, True),
        ("B2", True, False, False),
        ("B2", True, True, True),
        ("C1", True, True, False),
        ("C2", True, True, False),
        (None, True, True, False),
    ],
)
def test_cefr_destinations(tier: str | None, cefr_pass: bool, exception: bool, core: bool) -> None:
    menu = [
        MenuLevel(number, "test") for number in (1, 30, 150, 1000, 1018, 1300, 1399, 1499, 1500)
    ]
    levels = {
        item.level
        for item in review.destinations(
            menu, query(tier), cefr_pass=cefr_pass, b2_exception=exception
        )
    }
    assert (150 in levels) == core
    assert levels - {150} == {1000, 1018, 1300, 1399, 1499}


def response(guid: str, level: Any = 1018, fit: str = "good") -> dict[str, Any]:
    payload = dict(level=level, fit=fit, alternatives=[], reasoning="Disease transmission sense.")
    return dict(
        custom_id=guid,
        response=dict(
            status_code=200,
            body=dict(
                status="completed",
                output=[
                    dict(
                        type="message", content=[dict(type="output_text", text=json.dumps(payload))]
                    )
                ],
            ),
        ),
    )


def test_collection_is_durable_independent_and_retryable(tmp_path: Path) -> None:
    path = tmp_path / "review.sqlite"
    store = review.ReviewStore(path)
    for guid in ("vector-biology", "vector-maths"):
        store.put("sense:" + guid, dict(guid=guid, allowed=[1018, 1085, 1399], shortlist=[]))
    review.collect(store, [response("vector-biology"), response("vector-maths", 150)])
    assert store.get("sense:vector-biology")["suggestion"]["level"] == 1018
    assert "suggestion" not in store.get("sense:vector-maths")
    assert store.get("sense:vector-maths")["error"]
    review.collect(store, [response("vector-maths", 1085)])
    # Replayed results cannot overwrite a previously collected suggestion.
    review.collect(store, [response("vector-biology", 1085)])
    store.db.close()
    reopened = review.ReviewStore(path)
    assert reopened.get("sense:vector-biology")["suggestion"]["level"] == 1018
    assert reopened.get("sense:vector-maths")["suggestion"]["level"] == 1085
    reopened.db.close()


@pytest.mark.parametrize(
    "level,fit,valid",
    [(0, "none", True), (True, "good", False), (1018.1, "good", False), (1018, "bogus", False)],
)
def test_bad_or_no_fit_answers(tmp_path: Path, level: Any, fit: str, valid: bool) -> None:
    store = review.ReviewStore(tmp_path / "review.sqlite")
    store.put("sense:x", dict(guid="x", allowed=[1018, 1399], shortlist=[]))
    review.collect(store, [response("x", level, fit)])
    assert ("suggestion" in store.get("sense:x")) == valid
    if valid:
        assert store.get("sense:x")["suggestion"]["level"] is None
    store.db.close()


def session_with_lemma() -> tuple[Session, Lemma]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    lemma = Lemma(
        guid="test-guid",
        lemma_text="vector",
        definition_text="Disease carrier",
        pos_type="noun",
        pos_subtype="animal",
        difficulty_level=1085,
    )
    session.add(lemma)
    session.commit()
    return session, lemma


def test_preview_apply_and_stale_definition(tmp_path: Path) -> None:
    session, lemma = session_with_lemma()
    store = review.ReviewStore(tmp_path / "review.sqlite")
    placer = review.LevelPlacer(session, {})
    original = review.fingerprint(lemma, query_for_lemma(session, lemma, placer.index))
    store.put(
        "sense:test-guid",
        dict(guid=lemma.guid, fingerprint=original, allowed=[1018, 1399], shortlist=[]),
    )
    review.collect(store, [response("test-guid")])
    moves = review.approved_moves(session, store, {"test-guid": 1018})
    assert lemma.difficulty_level == 1085
    lemma.definition_text = "A mathematical quantity"
    session.commit()
    with pytest.raises(ValueError, match="Stale"):
        review.approved_moves(session, store, {"test-guid": 1018})
    lemma.definition_text = "Disease carrier"
    session.commit()
    apply_moves(session, moves, source="test-review")
    session.commit()
    assert lemma.difficulty_level == 1018
    with pytest.raises(ValueError, match="Stale"):
        review.approved_moves(session, store, {"test-guid": 1018})
    session.close()
    store.db.close()


def test_prepare_resumes_protects_old_and_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, lemma = session_with_lemma()
    other = Lemma(
        guid="core",
        lemma_text="norm",
        definition_text="a rule",
        pos_type="noun",
        difficulty_level=150,
    )
    session.add(other)
    session.commit()
    monkeypatch.setattr(
        review,
        "release_rows",
        lambda commit: {} if commit == "old" else {"test-guid": {}, "core": {}},
    )
    store = review.ReviewStore(tmp_path / "review.sqlite")
    assert review.prepare(session, store, "old", "new", "topics", "test-model") == 1
    saved = store.get("sense:test-guid")
    assert saved["current_level"] == 1085
    assert saved["request"]["custom_id"] == lemma.guid
    assert all(1000 <= number <= 1499 for number in saved["allowed"])
    assert review.prepare(session, store, "old", "new", "topics", "test-model") == 1
    assert store.get("sense:test-guid") == saved
    assert store.get("sense:core") is None
    with pytest.raises(ValueError, match="different settings"):
        review.prepare(session, store, "old", "new", "staging", "test-model")
    session.close()
    store.db.close()


def test_catalogue_rejects_occupied_untitled_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = session_with_lemma()
    monkeypatch.setattr(review, "release_rows", lambda commit: {})
    store = review.ReviewStore(tmp_path / "review.sqlite")
    with pytest.raises(ValueError, match="occupied"):
        review.prepare(
            session, store, "old", "new", "topics", "test-model", catalogue=[dict(level=1085)]
        )
    session.close()
    store.db.close()


def test_null_assignment_can_use_logged_move(tmp_path: Path) -> None:
    session, lemma = session_with_lemma()
    lemma.difficulty_level = None
    session.commit()
    store = review.ReviewStore(tmp_path / "review.sqlite")
    placer = review.LevelPlacer(session, {})
    store.put(
        "sense:test-guid",
        dict(
            guid=lemma.guid,
            allowed=[1018, 1399],
            shortlist=[],
            fingerprint=review.fingerprint(lemma, query_for_lemma(session, lemma, placer.index)),
        ),
    )
    review.collect(store, [response("test-guid", 0, "none")])
    moves = review.approved_moves(session, store, {"test-guid": 1399})
    assert moves[0].old_level is None
    apply_moves(session, moves, source="test-review")
    session.commit()
    assert lemma.difficulty_level == 1399
    session.close()
    store.db.close()


def test_cli_apply_backs_up_and_installs_approved_topic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    session, lemma = session_with_lemma()
    path = tmp_path / "review.sqlite"
    store = review.ReviewStore(path)
    placer = review.LevelPlacer(session, {})
    store.put(
        "settings",
        dict(catalogue=[dict(level=1018, name="Epidemiology", boundary="Disease transmission")]),
    )
    store.put(
        "sense:test-guid",
        dict(
            guid=lemma.guid,
            allowed=[1018, 1399],
            shortlist=[],
            fingerprint=review.fingerprint(lemma, query_for_lemma(session, lemma, placer.index)),
        ),
    )
    review.collect(store, [response("test-guid")])
    store.db.close()
    approvals = tmp_path / "approvals.json"
    approvals.write_text(json.dumps({"test-guid": 1018}))
    monkeypatch.setattr(review, "create_session", lambda config: session)
    backups: list[str] = []

    def backup(config: review.DataSourceConfig, label: str, tier: str) -> Path:
        assert lemma.difficulty_level == 1085
        backups.append(tier)
        return tmp_path / label

    monkeypatch.setattr(review, "create_backup", backup)
    monkeypatch.setattr(
        sys, "argv", ["review", "apply", "--review", str(path), "--approvals", str(approvals)]
    )
    review.main()
    assert backups == ["minor"]
    assert session.query(Lemma).filter(Lemma.guid == "test-guid").one().difficulty_level == 1018
    assert review.get_curriculum_level(session, 1018).name == "Epidemiology"  # type: ignore[union-attr]
    session.close()


def test_release_reader_ignores_blank_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    def output(args: list[str], **kwargs: Any) -> str:
        if args[1] == "ls-tree":
            return "data/release/lemmas/nouns/animal/base.jsonl\ndata/release/lemmas/nouns/animal/en.jsonl\n"
        return '\n{"guid":"a","difficulty_level":1399}\n\n'

    monkeypatch.setattr(review.subprocess, "check_output", output)
    assert review.release_rows("snapshot") == {"a": {"guid": "a", "difficulty_level": 1399}}


def test_install_topics_preserves_editorial_examples_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = session_with_lemma()
    backups: list[str] = []

    def backup(config: review.DataSourceConfig, label: str, tier: str) -> Path:
        backups.append(tier)
        return tmp_path / label

    monkeypatch.setattr(review, "create_backup", backup)
    catalogue = [
        dict(
            level=1042,
            name="Mechanics and Machines",
            boundary="Mechanical senses only.",
            examples=["differential (gearing)", "piston"],
        )
    ]
    config = review.DataSourceConfig(
        backend_type=review.BackendType.SQLITE, sqlite_path=str(tmp_path / "unused.sqlite")
    )
    assert review.install_topics(session, config, catalogue) == 1
    row = review.get_curriculum_level(session, 1042)
    assert row is not None
    assert row.notes == review.catalogue_notes(catalogue[0])
    assert "differential (gearing)" in (row.notes or "")
    session.commit()
    assert review.install_topics(session, config, catalogue) == 0
    assert backups == ["minor"]
    with pytest.raises(ValueError, match="occupied"):
        review.install_topics(session, config, [dict(level=1085, name="Occupied", boundary="test")])
    assert backups == ["minor"]
    session.close()


def test_single_run_persists_one_suggestion_without_moving(tmp_path: Path) -> None:
    from unittest.mock import Mock

    from clients.types import Response
    from storage.models.operation_log import OperationLog

    session, lemma = session_with_lemma()
    store = review.ReviewStore(tmp_path / "review.sqlite")
    placer = review.LevelPlacer(session, {})
    store.put("settings", dict(catalogue=[]))
    store.put(
        "sense:test-guid",
        dict(
            guid=lemma.guid,
            current_level=1085,
            allowed=[1018, 1399],
            shortlist=[],
            fingerprint=review.fingerprint(lemma, query_for_lemma(session, lemma, placer.index)),
            request=dict(
                body=dict(
                    model="gpt-5-mini",
                    input=[dict(role="user", content="Sense-specific prompt")],
                    text=dict(format=dict(schema=review.PLACEMENT_JSON_SCHEMA)),
                    max_output_tokens=4096,
                )
            ),
        ),
    )
    client = Mock(spec=review.OpenAIClient)
    client.generate_chat.return_value = Response(
        response_text="",
        structured_data=dict(
            level=1018, fit="good", alternatives=[], reasoning="Disease carrier sense belongs here."
        ),
        usage=None,
    )
    saved = review.run_one(session, store, "test-guid", client)
    assert saved["suggestion"]["level"] == 1018
    assert lemma.difficulty_level == 1085
    assert saved["single_attempt"]["status"] == "returned"
    assert (
        session.query(OperationLog)
        .filter(OperationLog.operation_type == "curriculum_placement_suggestion")
        .count()
        == 1
    )
    with pytest.raises(ValueError, match="Already attempted"):
        review.run_one(session, store, "test-guid", client)
    client.generate_chat.assert_called_once()
    session.close()
    store.db.close()


def test_prepare_accepts_registered_catalogue_and_uses_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = session_with_lemma()
    catalogue = [
        dict(
            level=1018, name="Epidemiology", boundary="Disease transmission.", examples=["pathogen"]
        )
    ]
    review.set_curriculum_level(
        session, 1018, "Epidemiology", notes=review.catalogue_notes(catalogue[0])
    )
    session.commit()
    monkeypatch.setattr(
        review, "release_rows", lambda commit: {} if commit == "old" else {"test-guid": {}}
    )
    store = review.ReviewStore(tmp_path / "review.sqlite")
    assert (
        review.prepare(session, store, "old", "new", "topics", "test-model", catalogue=catalogue)
        == 1
    )
    context = store.get("sense:test-guid")["request"]["body"]["input"][0]["content"]
    assert "Disease transmission." in context and "pathogen" in context
    assert context.count("1018 |") == 1
    session.close()
    store.db.close()


def test_apply_results_moves_and_recovers_after_journal_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from storage.models.operation_log import OperationLog

    session, lemma = session_with_lemma()
    review.set_curriculum_level(session, 1018, "Disease and Epidemiology")
    session.commit()
    store = review.ReviewStore(tmp_path / "review.sqlite")
    placer = review.LevelPlacer(session, {})
    store.put(
        "sense:test-guid",
        dict(
            guid=lemma.guid,
            current_level=1085,
            allowed=[1018, 1399],
            shortlist=[],
            fingerprint=review.fingerprint(lemma, query_for_lemma(session, lemma, placer.index)),
            request=dict(body=dict(model="gpt-5-mini")),
        ),
    )
    review.collect(store, [response("test-guid")])
    backups: list[str] = []

    def backup(config: review.DataSourceConfig, label: str, tier: str) -> Path:
        backups.append(tier)
        return tmp_path / label

    monkeypatch.setattr(review, "create_backup", backup)
    config = review.DataSourceConfig(
        backend_type=review.BackendType.SQLITE, sqlite_path=str(tmp_path / "unused")
    )
    assert review.apply_results(session, config, store) == dict(moved=1, kept=0, blocked=0)
    assert lemma.difficulty_level == 1018
    count = session.query(OperationLog).count()
    # Simulate primary commit followed by loss of the journal receipt.
    saved = store.get("sense:test-guid")
    saved.pop("applied")
    store.put("sense:test-guid", saved)
    assert review.apply_results(session, config, store) == dict(moved=0, kept=0, blocked=0)
    assert session.query(OperationLog).count() == count
    assert store.get("sense:test-guid")["applied"]["level"] == 1018
    assert backups == ["minor"]
    session.close()
    store.db.close()


@pytest.mark.parametrize("no_fit,stale,target", [(True, False, 1399), (False, True, 1085)])
def test_apply_results_parks_no_fit_and_blocks_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_fit: bool, stale: bool, target: int
) -> None:
    session, lemma = session_with_lemma()
    review.set_curriculum_level(session, 1018, "Epidemiology")
    session.commit()
    store = review.ReviewStore(tmp_path / "review.sqlite")
    placer = review.LevelPlacer(session, {})
    store.put(
        "sense:test-guid",
        dict(
            guid=lemma.guid,
            current_level=1085,
            allowed=[1018, 1399],
            shortlist=[],
            fingerprint=review.fingerprint(lemma, query_for_lemma(session, lemma, placer.index)),
            request=dict(body=dict(model="gpt-5-mini")),
        ),
    )
    review.collect(
        store, [response("test-guid", 0 if no_fit else 1018, "none" if no_fit else "good")]
    )
    if stale:
        lemma.definition_text = "Edited after submission"
        session.commit()
    monkeypatch.setattr(review, "create_backup", lambda *args, **kwargs: tmp_path / "backup")
    config = review.DataSourceConfig(
        backend_type=review.BackendType.SQLITE, sqlite_path=str(tmp_path / "unused")
    )
    result = review.apply_results(session, config, store)
    assert lemma.difficulty_level == target
    assert result["blocked"] == int(stale)
    session.close()
    store.db.close()


def test_collect_all_applies_terminal_jobs_and_waits_for_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    store = review.ReviewStore(tmp_path / "review.sqlite")
    store.put("batch_policy", dict(apply_on_collect=True))
    store.put("jobs", [dict(batch_id="done", guids=["x"]), dict(batch_id="waiting", guids=["y"])])
    store.put("sense:x", dict(guid="x", allowed=[1018, 1399], shortlist=[]))
    client = Mock(spec=review.OpenAIBatchClient)
    client.get_batch_status.side_effect = [
        dict(status="completed", output_file_id="out"),
        dict(status="in_progress"),
    ]
    client.download_batch_results.return_value = [response("x")]
    apply = Mock(return_value=dict(moved=1))
    monkeypatch.setattr(review, "apply_results", apply)
    config = review.DataSourceConfig(backend_type=review.BackendType.SQLITE, sqlite_path="unused")
    assert not review.collect_all(Mock(spec=Session), config, store, client)
    assert store.get("sense:x")["suggestion"]["level"] == 1018
    assert store.get("jobs")[0]["collected"]
    apply.assert_called_once()
    store.db.close()


def test_level_metadata_patch_preserves_existing_fields_and_reserves_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _ = session_with_lemma()
    review.set_curriculum_level(
        session,
        1042,
        "Mechanics",
        notes="Boundary and examples",
        extra={"icon": "gear"},
        prerequisites=[150],
    )
    session.commit()
    monkeypatch.setattr(review, "create_backup", lambda *args, **kwargs: tmp_path / "backup")
    config = review.DataSourceConfig(
        backend_type=review.BackendType.SQLITE, sqlite_path=str(tmp_path / "unused")
    )
    patch = [
        dict(level=1042, cefr="C1", expected_cefr=None),
        dict(level=1499, name="Advanced Abstract Concepts", cefr="C2"),
    ]
    assert review.update_levels(session, config, patch) == 2
    row = review.get_curriculum_level(session, 1042)
    assert row is not None
    assert row.name == "Mechanics" and row.cefr == "C1"
    assert row.notes == "Boundary and examples" and row.get_extra() == {"icon": "gear"}
    assert row.get_prerequisites() == [150]
    session.commit()
    assert review.update_levels(session, config, patch) == 0
    with pytest.raises(ValueError, match="reserved"):
        review.update_levels(
            session, config, [dict(level=1399, name="Not a real topic", cefr="C2")]
        )
    session.close()


def test_inventory_sample_is_frozen_and_does_not_read_release_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, lemma = session_with_lemma()
    lemma.difficulty_level = 1399
    for index in range(3):
        session.add(
            Lemma(
                guid=f"N72_sample{index}",
                lemma_text=f"sample-{index}",
                definition_text="A test sense.",
                pos_type="noun",
                difficulty_level=1399,
            )
        )
    session.commit()
    monkeypatch.setattr(
        review,
        "release_rows",
        lambda commit: (_ for _ in ()).throw(AssertionError("No release diff")),
    )
    store = review.ReviewStore(tmp_path / "sample.sqlite")
    assert (
        review.prepare(
            session, store, "old", "new", "staging", "gpt-5-mini", inventory=True, limit=2, seed=7
        )
        == 2
    )
    selection = store.get("selection")
    assert selection["population"] == 4 and len(selection["guids"]) == 2
    before = store.rows()
    assert (
        review.prepare(
            session, store, "old", "new", "staging", "gpt-5-mini", inventory=True, limit=2, seed=7
        )
        == 2
    )
    assert store.rows() == before
    assert store.get("selection") == selection
    for record in before:
        schema = record["request"]["body"]["text"]["format"]["schema"]
        assert schema["properties"]["level"]["enum"] == [0, *record["allowed"]]
        assert schema["properties"]["alternatives"]["items"]["enum"] == record["allowed"]
    store.db.close()
    session.close()


def test_stats_report_actual_destinations_and_unresolved_senses(tmp_path: Path) -> None:
    session, lemma = session_with_lemma()
    lemma.difficulty_level = 1042
    second = Lemma(
        guid="N72_waiting",
        lemma_text="waiting",
        definition_text="A test sense.",
        pos_type="noun",
        difficulty_level=1399,
    )
    session.add(second)
    review.set_curriculum_level(session, 1042, "Mechanics and Machines", cefr="C1")
    session.commit()
    store = review.ReviewStore(tmp_path / "stats.sqlite")
    store.put("sense:test-guid", dict(guid="test-guid", current_level=1399))
    store.put(
        "sense:N72_waiting",
        dict(
            guid="N72_waiting",
            current_level=1399,
            suggestion=dict(fit="none"),
            applied=dict(level=1399),
        ),
    )
    store.put("sense:N72_missing", dict(guid="N72_missing", current_level=1399))
    tracking = review.create_batch_database_session(str(tmp_path / "tracking.sqlite"))
    report = review.placement_stats(session, store, tracking)
    assert report["selected"] == 3 and report["missing"] == 1
    assert report["moved"] == 1 and report["still_staging"] == 1
    assert report["no_suitable_level"] == 1
    assert report["destinations"][0] == dict(
        level=1042, name="Mechanics and Machines", cefr="C1", count=1
    )
    tracking.close()
    store.db.close()
    session.close()


def test_prepare_cli_forwards_inventory_sample_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    from unittest.mock import Mock

    prepare = Mock(return_value=1400)
    monkeypatch.setattr(review, "prepare", prepare)
    monkeypatch.setattr(review, "create_session", lambda config: Mock())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "review",
            "prepare",
            "--review",
            str(tmp_path / "cli.sqlite"),
            "--phase",
            "staging",
            "--inventory",
            "--limit",
            "1400",
            "--seed",
            "20261117",
            "--cefr-pass",
        ],
    )
    review.main()
    assert prepare.call_args.kwargs["inventory"] is True
    assert prepare.call_args.kwargs["limit"] == 1400
    assert prepare.call_args.kwargs["seed"] == 20261117
    assert prepare.call_args.kwargs["cefr_pass"] is True
