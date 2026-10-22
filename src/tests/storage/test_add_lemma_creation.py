"""Tests that storage.crud.lemma.add_lemma logs a new lemma and gives it English forms.

add_lemma used to write neither, so every lemma a migration or script created
through it had no ``lemma_create`` entry and no DerivativeForm -- invisible to
token frequency and to the word-import duplicate guard until a later backfill.
"""

from __future__ import annotations

import json
from typing import Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.crud.lemma import add_lemma
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, DerivativeForm, Lemma
from storage.utils.guid import run_lemma_write


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def _create_logs(session: Session) -> List[OperationLog]:
    return session.query(OperationLog).filter(OperationLog.operation_type == "lemma_create").all()


def _english_forms(session: Session, lemma: Lemma) -> List[DerivativeForm]:
    return (
        session.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "en")
        .all()
    )


def _add_cat(session: Session, source: str | None = None) -> Lemma:
    return run_lemma_write(
        session,
        lambda: add_lemma(
            session,
            lemma_text="cat",
            definition_text="a small domesticated feline",
            pos_type="noun",
            pos_subtype="animal",
            source=source,
        ),
    )


def test_new_lemma_writes_one_create_log(session: Session) -> None:
    lemma = _add_cat(session)

    logs = _create_logs(session)
    assert len(logs) == 1
    assert logs[0].lemma_id == lemma.id
    assert logs[0].entity_guid == lemma.guid
    assert logs[0].source == "lemma-crud/add"
    fact = json.loads(logs[0].fact)
    assert fact["pos_type"] == "noun"
    assert fact["definition"] == "a small domesticated feline"


def test_create_log_uses_the_callers_source(session: Session) -> None:
    _add_cat(session, source="migration/test")

    assert [log.source for log in _create_logs(session)] == ["migration/test"]


def test_new_lemma_gets_its_english_base_form(session: Session) -> None:
    lemma = _add_cat(session)

    base_forms = [form for form in _english_forms(session, lemma) if form.is_base_form]
    assert [form.derivative_form_text for form in base_forms] == ["cat"]
    assert base_forms[0].word_token_id is not None


def test_new_noun_gets_its_mechanical_plural(session: Session) -> None:
    lemma = _add_cat(session)

    texts = {form.derivative_form_text for form in _english_forms(session, lemma)}
    assert "cats" in texts


def test_existing_lemma_is_neither_logged_nor_given_forms_again(session: Session) -> None:
    lemma = _add_cat(session)
    forms_before = len(_english_forms(session, lemma))

    again = _add_cat(session)

    assert again.id == lemma.id
    assert len(_create_logs(session)) == 1
    assert len(_english_forms(session, lemma)) == forms_before
