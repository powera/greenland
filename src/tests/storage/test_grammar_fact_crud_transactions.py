"""Tests that add_grammar_fact and delete_grammar_fact leave the transaction to the caller.

Both used to commit, and add_grammar_fact rolled the whole session back on a
duplicate -- so a preview that rolled back still left facts behind, and a
duplicate fact silently discarded the caller's other pending writes (the forms
words.forms.persistence had just stored, for one).
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.crud.grammar_fact import (
    add_grammar_fact,
    delete_grammar_fact,
    get_grammar_fact_value,
)
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import Base, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def _committed_lemma(session: Session, text: str = "scissors") -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text="a cutting tool", pos_type="noun")
    session.add(lemma)
    session.commit()
    return lemma


def test_add_does_not_commit(session: Session) -> None:
    lemma = _committed_lemma(session)

    fact = add_grammar_fact(session, lemma.id, "en", "number_type", "plurale_tantum")
    assert fact is not None
    assert get_grammar_fact_value(session, lemma.id, "en", "number_type") == "plurale_tantum"

    session.rollback()

    assert get_grammar_fact_value(session, lemma.id, "en", "number_type") is None


def test_duplicate_returns_none_and_keeps_the_existing_value(session: Session) -> None:
    lemma = _committed_lemma(session)
    add_grammar_fact(session, lemma.id, "en", "number_type", "plurale_tantum")
    session.commit()

    assert add_grammar_fact(session, lemma.id, "en", "number_type", "regular") is None
    assert get_grammar_fact_value(session, lemma.id, "en", "number_type") == "plurale_tantum"


def test_duplicate_keeps_the_callers_pending_writes(session: Session) -> None:
    lemma = _committed_lemma(session)
    add_grammar_fact(session, lemma.id, "en", "number_type", "plurale_tantum")
    session.commit()

    pending = Lemma(lemma_text="trousers", definition_text="a garment", pos_type="noun")
    session.add(pending)
    session.flush()
    add_grammar_fact(session, lemma.id, "en", "number_type", "regular")
    session.commit()

    assert session.query(Lemma).filter(Lemma.lemma_text == "trousers").count() == 1


def test_delete_does_not_commit(session: Session) -> None:
    lemma = _committed_lemma(session)
    add_grammar_fact(session, lemma.id, "en", "number_type", "plurale_tantum")
    session.commit()

    assert delete_grammar_fact(session, lemma.id, "en", "number_type") is True
    assert get_grammar_fact_value(session, lemma.id, "en", "number_type") is None

    session.rollback()

    assert session.query(GrammarFact).count() == 1


def test_delete_of_a_missing_fact_returns_false(session: Session) -> None:
    lemma = _committed_lemma(session)

    assert delete_grammar_fact(session, lemma.id, "en", "number_type") is False
