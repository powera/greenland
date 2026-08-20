"""Tests for the GUID-keyed operation log helpers (storage.crud.operation_log).

The operation log is written from CRUD functions that take an optional ``source``
argument: passing one means "log this", passing nothing means "do not". These
tests cover that opt-in contract, the GUID-based entity reference that replaced
the old ``entity_id``-into-``lemma_id`` aliasing, and the flush-not-commit
semantics that keep an entry in the same transaction as the write it describes.
"""

from __future__ import annotations

import json
from dataclasses import fields
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.backend.jsonl import models as jsonl_models
from storage.crud.operation_log import (
    FieldChange,
    log_batch_operation,
    log_entity_operation,
    log_field_changes,
    log_operation,
)
from storage.models.operation_log import OperationLog
from storage.models.schema import Base


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _logs(db: Session) -> List[OperationLog]:
    return db.query(OperationLog).order_by(OperationLog.id).all()


def _fact(entry: OperationLog) -> dict:
    return json.loads(entry.fact)


# ── log_entity_operation ───────────────────────────────────────────────────


def test_entity_guid_is_stored_in_its_own_column(session: Session) -> None:
    log_entity_operation(
        session,
        source="test",
        operation_type="sentence_create",
        entity_guid="S_00001",
    )

    (entry,) = _logs(session)
    assert entry.entity_guid == "S_00001"
    # The GUID lives in the column, not duplicated into the fact JSON.
    assert "entity_guid" not in _fact(entry)
    # And it does not land in lemma_id the way log_operation's aliasing did.
    assert entry.lemma_id is None


@pytest.mark.parametrize(
    "guid,expected_kind",
    [
        ("S_00001", "sentence"),
        ("N02_001", "lemma"),
        ("M01_004", "idiom"),
        ("E04_007", "name"),
        ("F01_003", "phrase"),
    ],
)
def test_entity_kind_is_derived_from_the_guid_prefix(
    session: Session, guid: str, expected_kind: str
) -> None:
    log_entity_operation(session, source="test", operation_type="thing_create", entity_guid=guid)

    (entry,) = _logs(session)
    assert _fact(entry)["entity_kind"] == expected_kind


def test_none_values_are_stripped_but_empty_lists_survive(session: Session) -> None:
    log_entity_operation(
        session,
        source="test",
        operation_type="sentence_update",
        entity_guid="S_00001",
        fact={"kept": [], "dropped": None, "also_kept": 0},
    )

    fact = _fact(_logs(session)[0])
    assert "dropped" not in fact
    # An empty list is how "the last value was removed" is recorded, so the
    # None-stripping must not take it with it.
    assert fact["kept"] == []
    assert fact["also_kept"] == 0


def test_the_callers_fact_mapping_is_not_mutated(session: Session) -> None:
    caller_fact = {"language_code": "lt"}

    log_entity_operation(
        session,
        source="test",
        operation_type="sentence_update",
        entity_guid="S_00001",
        fact=caller_fact,
    )

    # log_operation() writes entity_type straight into the dict it was handed;
    # these helpers must copy instead.
    assert caller_fact == {"language_code": "lt"}


def test_entry_is_flushed_but_not_committed(session: Session) -> None:
    log_entity_operation(
        session, source="test", operation_type="sentence_create", entity_guid="S_00001"
    )

    # Visible inside the transaction ...
    assert len(_logs(session)) == 1

    session.rollback()

    # ... and gone with it, so a rolled-back write cannot leave a log claiming
    # it happened.
    assert _logs(session) == []


# ── log_field_changes ──────────────────────────────────────────────────────


def test_field_changes_writes_nothing_without_a_source(session: Session) -> None:
    result = log_field_changes(
        session,
        source=None,
        operation_type="sentence_update",
        entity_guid="S_00001",
        changes=[FieldChange("verified", False, True)],
    )

    assert result is None
    assert _logs(session) == []


def test_field_changes_drops_unchanged_fields(session: Session) -> None:
    log_field_changes(
        session,
        source="test",
        operation_type="sentence_update",
        entity_guid="S_00001",
        changes=[
            FieldChange("verified", False, True),
            FieldChange("tense", "past", "past"),
        ],
    )

    fact = _fact(_logs(session)[0])
    assert fact["changed_fields"] == ["verified"]
    assert fact["changes"] == [{"field": "verified", "old_value": False, "new_value": True}]


def test_field_changes_writes_nothing_when_nothing_changed(session: Session) -> None:
    result = log_field_changes(
        session,
        source="test",
        operation_type="sentence_update",
        entity_guid="S_00001",
        changes=[FieldChange("tense", "past", "past")],
    )

    # A no-op update must not leave an entry claiming an edit occurred.
    assert result is None
    assert _logs(session) == []


def test_field_changes_merges_extra_keys(session: Session) -> None:
    log_field_changes(
        session,
        source="test",
        operation_type="sentence_translation_update",
        entity_guid="S_00001",
        changes=[FieldChange("translation_text", "labas", "sveiki")],
        extra={"language_code": "lt"},
    )

    assert _fact(_logs(session)[0])["language_code"] == "lt"


# ── log_batch_operation ────────────────────────────────────────────────────


def test_batch_operation_no_ops_without_a_source(session: Session) -> None:
    assert (
        log_batch_operation(
            session,
            source=None,
            operation_type="sentence_word_create",
            entity_guid="S_00001",
            count=7,
        )
        is None
    )
    assert _logs(session) == []


def test_batch_operation_no_ops_on_an_empty_batch(session: Session) -> None:
    assert (
        log_batch_operation(
            session,
            source="test",
            operation_type="sentence_word_create",
            entity_guid="S_00001",
            count=0,
        )
        is None
    )
    assert _logs(session) == []


def test_batch_operation_records_the_count(session: Session) -> None:
    log_batch_operation(
        session,
        source="test",
        operation_type="sentence_word_create",
        entity_guid="S_00001",
        count=7,
        fact={"language_code": "lt"},
    )

    fact = _fact(_logs(session)[0])
    assert fact["count"] == 7
    assert fact["language_code"] == "lt"


# ── backward compatibility ─────────────────────────────────────────────────


def test_log_operation_still_aliases_entity_id_into_lemma_id(session: Session) -> None:
    """The legacy writer keeps its exact behavior; ~80 call sites depend on it."""
    log_operation(
        session,
        operation_type="lemma_create",
        source="test",
        entity_id=42,
    )

    (entry,) = _logs(session)
    assert entry.lemma_id == 42


def test_log_operation_accepts_an_entity_guid(session: Session) -> None:
    log_operation(
        session,
        operation_type="lemma_create",
        source="test",
        lemma_id=42,
        entity_guid="N02_001",
    )

    (entry,) = _logs(session)
    assert entry.entity_guid == "N02_001"
    # lemma_id stays populated: the SERNAS synonym-scan state reads key on it.
    assert entry.lemma_id == 42


def test_a_legacy_row_without_an_entity_guid_reads_back(session: Session) -> None:
    session.add(OperationLog(source="legacy", operation_type="translation", fact="{}", lemma_id=1))
    session.flush()

    (entry,) = _logs(session)
    assert entry.entity_guid is None


# ── JSONL mirror ───────────────────────────────────────────────────────────


def test_jsonl_mirror_round_trips_entity_guid() -> None:
    log = jsonl_models.OperationLog(
        id=1,
        source="test",
        operation_type="sentence_create",
        fact="{}",
        entity_guid="S_00001",
    )

    data = log.to_dict()
    assert data["entity_guid"] == "S_00001"
    assert jsonl_models.OperationLog.from_dict(data).entity_guid == "S_00001"


def test_jsonl_mirror_defaults_entity_guid_for_older_lines() -> None:
    """A file written before the column existed must still load."""
    log = jsonl_models.OperationLog.from_dict(
        {"id": 1, "source": "test", "operation_type": "translation", "fact": "{}"}
    )

    assert log.entity_guid is None


def test_jsonl_mirror_ignores_unknown_keys() -> None:
    """A line from a newer schema must not abort the load.

    JSONLStorage._load_operation_logs wraps its entire file loop in a bare
    except, so a TypeError here would silently drop every log in the file, not
    just the offending line.
    """
    log = jsonl_models.OperationLog.from_dict(
        {
            "id": 1,
            "source": "test",
            "operation_type": "translation",
            "fact": "{}",
            "a_column_from_the_future": "boom",
        }
    )

    assert log.id == 1
    assert "a_column_from_the_future" not in {f.name for f in fields(log)}
