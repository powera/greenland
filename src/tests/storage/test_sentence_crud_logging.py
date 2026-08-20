"""Tests for operation logging in the sentence CRUD functions.

Every write here is opt-in: passing ``source`` means "log this", omitting it
means "do not". These tests pin both halves of that contract, plus the ordering
constraints that make a delete auditable -- the entry has to be written while
the row is still readable, and has to survive the row it describes.
"""

from __future__ import annotations

import json
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.crud.operation_log import (
    SENTENCE_CREATE,
    SENTENCE_DELETE,
    SENTENCE_MERGE,
    SENTENCE_TRANSLATION_CREATE,
    SENTENCE_TRANSLATION_DELETE,
    SENTENCE_TRANSLATION_UPDATE,
    SENTENCE_UPDATE,
)
from storage.crud.sentence import (
    add_sentence,
    delete_sentence,
    merge_duplicate_sentences,
    update_sentence,
)
from storage.crud.sentence_translation import (
    add_sentence_translation,
    delete_sentence_translation,
    get_or_create_sentence_translation,
    update_sentence_translation,
)
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, Sentence

SOURCE = "test-suite"


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _logs(db: Session, operation_type: str) -> List[OperationLog]:
    return (
        db.query(OperationLog)
        .filter(OperationLog.operation_type == operation_type)
        .order_by(OperationLog.id)
        .all()
    )


def _fact(entry: OperationLog) -> dict:
    return json.loads(entry.fact)


def _log_count(db: Session) -> int:
    return db.query(OperationLog).count()


# ── sentences ──────────────────────────────────────────────────────────────


def test_add_sentence_logs_against_its_guid(session: Session) -> None:
    sentence = add_sentence(session, pattern_type="SVO", source=SOURCE)

    (entry,) = _logs(session, SENTENCE_CREATE)
    assert entry.entity_guid == sentence.guid
    assert entry.source == SOURCE
    assert _fact(entry)["entity_kind"] == "sentence"
    assert _fact(entry)["pattern_type"] == "SVO"


def test_update_sentence_records_only_what_changed(session: Session) -> None:
    sentence = add_sentence(session, pattern_type="SVO", tense="past")

    update_sentence(session, sentence, tense="past", verified=True, source=SOURCE)

    (entry,) = _logs(session, SENTENCE_UPDATE)
    # tense was rewritten with the value it already had, so it is not a change.
    assert _fact(entry)["changed_fields"] == ["verified"]
    assert _fact(entry)["changes"] == [{"field": "verified", "old_value": False, "new_value": True}]


def test_update_sentence_logs_nothing_when_nothing_changed(session: Session) -> None:
    sentence = add_sentence(session, pattern_type="SVO")

    update_sentence(session, sentence, pattern_type="SVO", source=SOURCE)

    assert _logs(session, SENTENCE_UPDATE) == []


def test_omitted_fields_are_not_treated_as_changes(session: Session) -> None:
    """A None argument means "leave this alone", not "set it to None"."""
    sentence = add_sentence(session, pattern_type="SVO", tense="past", notes="hi")

    update_sentence(session, sentence, verified=True, source=SOURCE)

    (entry,) = _logs(session, SENTENCE_UPDATE)
    assert _fact(entry)["changed_fields"] == ["verified"]
    assert sentence.tense == "past"
    assert sentence.notes == "hi"


def test_delete_sentence_snapshots_counts_and_outlives_the_row(session: Session) -> None:
    sentence = add_sentence(session, pattern_type="SVO")
    add_sentence_translation(session, sentence, "en", "The dog runs.")
    guid = sentence.guid

    delete_sentence(session, sentence, source=SOURCE)
    session.commit()

    (entry,) = _logs(session, SENTENCE_DELETE)
    assert entry.entity_guid == guid
    # Counted before the cascade took them.
    assert _fact(entry)["translation_count"] == 1
    # The row is gone; the entry is not.
    assert session.query(Sentence).filter(Sentence.guid == guid).first() is None


def test_merge_logs_the_merge_and_each_absorbed_guid(session: Session) -> None:
    keep = add_sentence(session, pattern_type="SVO")
    dup_one = add_sentence(session, pattern_type="SVO")
    dup_two = add_sentence(session, pattern_type="SVO")
    dup_guids = [dup_one.guid, dup_two.guid]

    merge_duplicate_sentences(session, keep.id, [dup_one.id, dup_two.id], source=SOURCE)

    (merge_entry,) = _logs(session, SENTENCE_MERGE)
    assert merge_entry.entity_guid == keep.guid
    assert _fact(merge_entry)["merged_guids"] == dup_guids
    assert _fact(merge_entry)["counts"]["sentences_deleted"] == 2

    # Each absorbed GUID gets its own entry saying where it went, so looking up
    # a merged-away GUID still has an answer.
    delete_entries = _logs(session, SENTENCE_DELETE)
    assert [e.entity_guid for e in delete_entries] == dup_guids
    assert all(_fact(e)["merged_into"] == keep.guid for e in delete_entries)


# ── sentence translations ──────────────────────────────────────────────────


def test_add_translation_logs_against_the_sentence_guid(session: Session) -> None:
    sentence = add_sentence(session, pattern_type="SVO")

    add_sentence_translation(session, sentence, "lt", "Šuo bėga.", source=SOURCE)

    (entry,) = _logs(session, SENTENCE_TRANSLATION_CREATE)
    assert entry.entity_guid == sentence.guid
    assert _fact(entry)["language_code"] == "lt"
    assert _fact(entry)["new_value"] == "Šuo bėga."


def test_update_translation_records_the_old_and_new_text(session: Session) -> None:
    sentence = add_sentence(session, pattern_type="SVO")
    translation = add_sentence_translation(session, sentence, "lt", "Šuo bėga.")

    update_sentence_translation(session, translation, translation_text="Šuo laksto.", source=SOURCE)

    (entry,) = _logs(session, SENTENCE_TRANSLATION_UPDATE)
    assert entry.entity_guid == sentence.guid
    assert _fact(entry)["language_code"] == "lt"
    assert _fact(entry)["changes"] == [
        {
            "field": "translation_text",
            "old_value": "Šuo bėga.",
            "new_value": "Šuo laksto.",
        }
    ]


def test_delete_translation_captures_the_text_before_removing_it(
    session: Session,
) -> None:
    sentence = add_sentence(session, pattern_type="SVO")
    translation = add_sentence_translation(session, sentence, "lt", "Šuo bėga.")

    delete_sentence_translation(session, translation, source=SOURCE)

    (entry,) = _logs(session, SENTENCE_TRANSLATION_DELETE)
    assert _fact(entry)["old_value"] == "Šuo bėga."


def test_get_or_create_logs_only_when_it_creates(session: Session) -> None:
    sentence = add_sentence(session, pattern_type="SVO")

    _, created = get_or_create_sentence_translation(
        session, sentence, "lt", "Šuo bėga.", source=SOURCE
    )
    assert created is True
    assert len(_logs(session, SENTENCE_TRANSLATION_CREATE)) == 1

    _, created_again = get_or_create_sentence_translation(
        session, sentence, "lt", "Šuo bėga.", source=SOURCE
    )
    assert created_again is False
    # Returning an existing row is not an edit and must not look like one.
    assert len(_logs(session, SENTENCE_TRANSLATION_CREATE)) == 1


# ── the opt-in contract ────────────────────────────────────────────────────


def test_no_source_means_no_logging_anywhere(session: Session) -> None:
    """Every path above, with source omitted, must leave the log table empty."""
    keep = add_sentence(session, pattern_type="SVO")
    dup = add_sentence(session, pattern_type="SVO")

    update_sentence(session, keep, verified=True)
    translation = add_sentence_translation(session, keep, "lt", "Šuo bėga.")
    update_sentence_translation(session, translation, translation_text="Šuo laksto.")
    get_or_create_sentence_translation(session, keep, "fr", "Le chien court.")
    delete_sentence_translation(session, translation)
    merge_duplicate_sentences(session, keep.id, [dup.id])
    delete_sentence(session, keep)

    assert _log_count(session) == 0
