"""Regular-queue placement submission, Barsukas dispatch, and safe application."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    create_batch_database_session,
    request_extra,
)
from clients.openai.batch_client import OpenAIBatchClient
from workqueue.handlers import level_placement as batch
from quality import curriculum_review as review
from reports.level_candidates import load_level_index, query_for_lemma
from storage.models.schema import Base, Lemma
from storage.models.operation_log import OperationLog
from workqueue.llm_batch import complete_rows
from workqueue.registry import get_llm_job


def setup_review(
    tmp_path: Path, count: int = 3
) -> tuple[Session, Session, review.ReviewStore, BatchQueueManager, Mock]:
    engine = create_engine(f"sqlite:///{tmp_path / 'main.sqlite'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    review.set_curriculum_level(session, 1042, "Mechanics and Machines")
    store = review.ReviewStore(tmp_path / "review.sqlite")
    store.put("settings", dict(phase="topics", model="gpt-5-mini", catalogue=[]))
    store.put("prepared", True)
    for index in range(count):
        lemma = Lemma(
            guid=f"N72_{index:03}",
            lemma_text=f"gear-{index}",
            definition_text="A vehicle gear mechanism.",
            pos_type="noun",
            pos_subtype="machine_part",
            difficulty_level=1085,
            frequency_rank=4000,
        )
        session.add(lemma)
        session.flush()
        store.put(
            "sense:" + str(lemma.guid),
            dict(
                guid=lemma.guid,
                current_level=1085,
                allowed=[1042, 1085, 1399],
                shortlist=[],
                fingerprint=review.fingerprint(
                    lemma, query_for_lemma(session, lemma, load_level_index(session))
                ),
                request=dict(
                    body=dict(
                        model="gpt-5-mini",
                        input=[
                            dict(role="system", content="Approved topic catalogue"),
                            dict(role="user", content=f"GUID {lemma.guid}: vehicle gear mechanism"),
                        ],
                        text=dict(format=dict(schema=review.PLACEMENT_JSON_SCHEMA)),
                        max_output_tokens=4096,
                    )
                ),
            ),
        )
    session.commit()
    tracking = create_batch_database_session(str(tmp_path / "tracking.sqlite"))
    client = Mock(spec=OpenAIBatchClient)
    client.upload_batch_file.side_effect = lambda requests: "file-" + str(
        client.upload_batch_file.call_count
    )
    client.create_batch.side_effect = lambda *args, **kwargs: dict(
        id="batch-" + str(client.create_batch.call_count)
    )
    manager = BatchQueueManager(tracking, client)
    return session, tracking, store, manager, client


def answer(level: int = 1042, fit: str = "good") -> dict[str, Any]:
    return dict(
        level=level, fit=fit, alternatives=[], reasoning="The defined sense is a machine component."
    )


def finish(tracking: Session, batch_id: str, data: dict[str, Any]) -> list[BatchQueue]:
    rows = tracking.query(BatchQueue).filter(BatchQueue.batch_id == batch_id).all()
    for row in rows:
        row.status = "completed"
        row.response_body = json.dumps(
            dict(
                body=dict(
                    status="completed",
                    output=[
                        dict(
                            type="message",
                            content=[dict(type="output_text", text=json.dumps(data))],
                        )
                    ],
                )
            )
        )
    tracking.commit()
    return rows


def test_queue_rows_visible_and_dispatch_applies_once_without_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from barsukas.batch_poller import apply_completed_requests

    session, tracking, store, manager, client = setup_review(tmp_path)
    backups: list[str] = []

    def backup(config: review.DataSourceConfig, label: str, tier: str) -> Path:
        assert config.sqlite_path == str(tmp_path / "main.sqlite")
        backups.append(tier)
        return tmp_path / "backup"

    monkeypatch.setattr(batch, "create_backup", backup)
    assert get_llm_job("curriculum_review") is batch.PLACEMENT_JOB
    ids = review.submit_all(session, store, manager, 2, apply_on_collect=True)
    assert len(ids) == 2
    rows = tracking.query(BatchQueue).all()
    assert len(rows) == 3
    assert {row.agent_name for row in rows} == {"curriculum_review"}
    assert {row.operation_type for row in rows} == {"levels.placement"}
    assert all(row.entity_id is not None and row.entity_type == "lemma" for row in rows)
    assert sorted(len(call.args[0]) for call in client.upload_batch_file.call_args_list) == [1, 2]
    # The shared runner skips in-flight items on a resumed script invocation.
    assert review.submit_all(session, store, manager, 2, apply_on_collect=True) == []
    assert client.create_batch.call_count == 2
    store.db.close()
    (tmp_path / "review.sqlite").unlink()
    completed = finish(tracking, ids[0], answer())
    result = apply_completed_requests("curriculum_review", completed, session, ids[0])
    assert result["updated"] == 2
    assert session.query(Lemma).filter(Lemma.difficulty_level == 1042).count() == 2
    assert backups == ["minor"]
    log_count = session.query(OperationLog).count()
    result = apply_completed_requests("curriculum_review", completed, session, ids[0])
    assert result["processed"] == 0
    # Recover the primary commit / tracking-commit gap without a second move or backup.
    for row in completed:
        extra = request_extra(row)
        extra.pop("applied", None)
        metadata = json.loads(row.additional_metadata or "{}")
        metadata["extra"] = extra
        row.additional_metadata = json.dumps(metadata)
    tracking.commit()
    complete_rows(batch.PLACEMENT_JOB, completed, session, ids[0], manager)
    assert session.query(OperationLog).count() == log_count
    assert backups == ["minor"]
    session.close()
    tracking.close()


@pytest.mark.parametrize("case", ["stale", "invalid", "none", "suggest-only"])
def test_completion_safety_and_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    session, tracking, store, manager, _ = setup_review(tmp_path, 1)
    monkeypatch.setattr(batch, "create_backup", lambda *args, **kwargs: tmp_path / "backup")
    ids = review.submit_all(session, store, manager, 325, apply_on_collect=case != "suggest-only")
    if case == "stale":
        session.query(Lemma).one().definition_text = "Edited while the batch was running"
        session.commit()
    data = answer(
        1 if case == "invalid" else (0 if case == "none" else 1042),
        "none" if case == "none" else "good",
    )
    rows = finish(tracking, ids[0], data)
    result = complete_rows(batch.PLACEMENT_JOB, rows, session, ids[0], manager)
    assert session.query(Lemma).one().difficulty_level == (1399 if case == "none" else 1085)
    if case == "invalid":
        assert result["failed"] == 1
    if case == "stale":
        assert result["skipped"] == 1
    review.refresh_results(session, store)
    if case != "invalid":
        assert store.rows()[0]["suggestion"]["reasoning"]
    if case == "none":
        assert store.rows()[0]["applied"]["level"] == 1399
    session.close()
    tracking.close()
    store.db.close()


def test_dry_run_uses_no_remote_client_and_writes_no_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tracking, store, _, _ = setup_review(tmp_path)
    factory = Mock(side_effect=AssertionError("Dry run must not load credentials"))
    monkeypatch.setattr("clients.batch_queue.OpenAIBatchClient", factory)
    manager = BatchQueueManager(tracking)
    before = session.query(OperationLog).count()
    assert (
        review.submit_all(session, store, manager, 325, apply_on_collect=True, dry_run=True) == []
    )
    factory.assert_not_called()
    assert tracking.query(BatchQueue).count() == 0
    assert session.query(OperationLog).count() == before
    assert store.get("queue_runs") is None
    session.close()
    tracking.close()
    store.db.close()


def test_completion_balances_family_while_preserving_model_suggestion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, tracking, store, manager, _ = setup_review(tmp_path, 1)
    for level, name in (
        (1300, "Advanced Character, Thought and Feelings"),
        (1310, "Advanced Character, Thought and Feelings 2"),
        (1311, "Advanced Character, Thought and Feelings 3"),
    ):
        review.set_curriculum_level(
            session, level, name, cefr="C1", notes="Identical subject boundary"
        )
    session.add(
        Lemma(
            guid="N72_existing",
            lemma_text="already taught",
            definition_text="Character sense.",
            pos_type="noun",
            difficulty_level=1300,
        )
    )
    session.commit()
    record = store.rows()[0]
    record["allowed"] = [1300, 1310, 1311, 1399]
    store.put("sense:" + record["guid"], record)
    monkeypatch.setattr(batch, "create_backup", lambda *args, **kwargs: tmp_path / "backup")
    ids = review.submit_all(session, store, manager, 350, apply_on_collect=True)
    rows = finish(tracking, ids[0], answer(1300))
    result = complete_rows(batch.PLACEMENT_JOB, rows, session, ids[0], manager)
    assert result["updated"] == 1
    assert session.query(Lemma).filter(Lemma.guid == record["guid"]).one().difficulty_level == 1310
    receipt = (
        session.query(OperationLog)
        .filter(OperationLog.operation_type == "curriculum_placement_applied")
        .one()
    )
    fact = json.loads(receipt.fact)
    assert fact["suggested_level"] == 1300 and fact["level"] == 1310
    assert fact["suggestion"]["level"] == 1300
    session.close()
    tracking.close()
    store.db.close()
