"""Tests for the lemma tag helpers (storage.crud.lemma_tags).

``Lemma.tags`` is a JSON array that ``create_lemma`` could set but nothing could
subsequently amend. These tests cover the add/remove/set helpers, the
normalization that keeps ``Legal`` and ``legal`` from both accumulating, the
tolerance for the bare-string values older barsukas builds wrote into the
column, and the operation-log record that makes a hard delete auditable.
"""

from __future__ import annotations

import json

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.crud.lemma_tags import (
    TAG_OPERATION_TYPE,
    add_tags,
    normalize_tags,
    parse_tags_input,
    read_tags,
    remove_tags,
    serialize_tags_for_column,
    set_tags,
)
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _make_lemma(db: Session, text: str = "probate") -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text=f"{text}.", pos_type="noun")
    db.add(lemma)
    db.commit()
    return lemma


def _tag_logs(db: Session) -> list[OperationLog]:
    return (
        db.query(OperationLog)
        .filter(OperationLog.operation_type == TAG_OPERATION_TYPE)
        .order_by(OperationLog.id)
        .all()
    )


# ── normalization ──────────────────────────────────────────────────────────


def test_normalize_lowercases_dedupes_and_sorts() -> None:
    assert normalize_tags([" Legal ", "legal", "ARCHAIC"]) == ["archaic", "legal"]


def test_normalize_drops_empty_entries() -> None:
    assert normalize_tags(["legal", "", "   "]) == ["legal"]


# ── reading ────────────────────────────────────────────────────────────────


def test_read_tags_of_untagged_lemma_is_empty(session: Session) -> None:
    assert read_tags(_make_lemma(session)) == []


def test_read_tags_parses_json_array(session: Session) -> None:
    lemma = _make_lemma(session)
    lemma.tags = json.dumps(["legal", "archaic"])
    assert read_tags(lemma) == ["archaic", "legal"]


def test_read_tags_tolerates_legacy_bare_string(session: Session) -> None:
    """The barsukas edit form stored raw input for a period; it must still read."""
    lemma = _make_lemma(session)
    lemma.tags = "legal"
    assert read_tags(lemma) == ["legal"]


# ── mutation ───────────────────────────────────────────────────────────────


def test_add_tags_stores_json_array(session: Session) -> None:
    lemma = _make_lemma(session)
    assert add_tags(session, lemma, ["legal"]) == ["legal"]
    assert lemma.tags is not None
    assert json.loads(lemma.tags) == ["legal"]


def test_add_tags_keeps_existing_tags(session: Session) -> None:
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal"])
    assert add_tags(session, lemma, ["archaic"]) == ["archaic", "legal"]


def test_adding_a_duplicate_tag_is_a_noop(session: Session) -> None:
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal"])
    add_tags(session, lemma, ["LEGAL"])
    assert read_tags(lemma) == ["legal"]
    assert len(_tag_logs(session)) == 1, "a no-op must not be logged"


def test_remove_tags_hard_deletes(session: Session) -> None:
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal", "archaic"])
    assert remove_tags(session, lemma, ["legal"]) == ["archaic"]
    assert lemma.tags is not None
    assert json.loads(lemma.tags) == ["archaic"]


def test_removing_last_tag_nulls_the_column(session: Session) -> None:
    """Empty and NULL must not both mean "no tags"; create_lemma writes NULL."""
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal"])
    assert remove_tags(session, lemma, ["legal"]) == []
    assert lemma.tags is None


def test_removing_absent_tag_is_a_noop(session: Session) -> None:
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal"])
    remove_tags(session, lemma, ["medical"])
    assert read_tags(lemma) == ["legal"]
    assert len(_tag_logs(session)) == 1


def test_set_tags_replaces_the_whole_list(session: Session) -> None:
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal", "archaic"])
    assert set_tags(session, lemma, ["medical"]) == ["medical"]


# ── logging ────────────────────────────────────────────────────────────────


def test_addition_is_logged_with_old_and_new(session: Session) -> None:
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal"], source="genys/iowa-633")

    logs = _tag_logs(session)
    assert len(logs) == 1
    assert logs[0].source == "genys/iowa-633"
    assert logs[0].lemma_id == lemma.id
    fact = json.loads(logs[0].fact)
    assert fact["old_tags"] == []
    assert fact["new_tags"] == ["legal"]
    assert fact["added_tags"] == ["legal"]


def test_removal_is_logged_even_when_it_empties_the_list(session: Session) -> None:
    """A hard delete is only auditable if the emptied array survives logging.

    log_operation() strips None from the fact JSON, so the removal is recorded
    as an empty list rather than a null.
    """
    lemma = _make_lemma(session)
    add_tags(session, lemma, ["legal"])
    remove_tags(session, lemma, ["legal"])

    fact = json.loads(_tag_logs(session)[-1].fact)
    assert fact["old_tags"] == ["legal"]
    assert fact["new_tags"] == []
    assert fact["removed_tags"] == ["legal"]


# ── form input parsing ─────────────────────────────────────────────────────


def test_parse_accepts_comma_separated() -> None:
    assert parse_tags_input("legal, archaic") == ["archaic", "legal"]


def test_parse_accepts_json_array() -> None:
    assert parse_tags_input('["legal", "archaic"]') == ["archaic", "legal"]


def test_parse_empty_input_is_empty_list() -> None:
    assert parse_tags_input("   ") == []


@pytest.mark.parametrize("bad", ['{"legal": true}', "[1, [2]]", "[unquoted]"])
def test_parse_rejects_malformed_json(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_tags_input(bad)


def test_serialize_empty_is_none() -> None:
    assert serialize_tags_for_column([]) is None
