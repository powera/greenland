"""CRUD and registry tests for language-independent lemma facts."""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401 -- register every model before create_all
from storage.config.lemma_fact_registry import validate_lemma_fact
from storage.crud.lemma import add_lemma
from storage.crud.lemma_fact import (
    add_lemma_fact,
    delete_lemma_fact,
    get_lemma_fact_value,
    get_lemma_facts,
    get_lemma_facts_dict,
    get_quantifiable,
)
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Base, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def _noun(session: Session, text: str = "bear") -> Lemma:
    return add_lemma(
        session,
        lemma_text=text,
        definition_text=f"a {text}",
        pos_type="noun",
        auto_generate_guid=False,
    )


def test_unclassified_lemma_is_none(session: Session) -> None:
    lemma = _noun(session)

    assert get_quantifiable(session, lemma.id) is None
    assert get_lemma_facts(session, lemma.id) == []


def test_add_and_read_back(session: Session) -> None:
    lemma = _noun(session)

    fact = add_lemma_fact(session, lemma.id, "quantifiable", "true", notes="units", verified=True)

    assert fact is not None
    assert get_lemma_fact_value(session, lemma.id, "quantifiable") == "true"
    assert get_quantifiable(session, lemma.id) is True
    assert get_lemma_facts_dict(session, lemma.id) == {"quantifiable": "true"}


def test_false_is_distinct_from_unclassified(session: Session) -> None:
    lemma = _noun(session, "rice")

    add_lemma_fact(session, lemma.id, "quantifiable", "false")

    assert get_quantifiable(session, lemma.id) is False


def test_add_replaces_existing_value(session: Session) -> None:
    lemma = _noun(session)
    add_lemma_fact(session, lemma.id, "quantifiable", "false", notes="first")

    add_lemma_fact(session, lemma.id, "quantifiable", "true", notes=None)

    facts = get_lemma_facts(session, lemma.id)
    assert len(facts) == 1
    assert facts[0].fact_value == "true"
    assert facts[0].notes is None


def test_invalid_value_is_rejected_without_writing(session: Session) -> None:
    lemma = _noun(session)

    assert add_lemma_fact(session, lemma.id, "quantifiable", "maybe") is None
    assert get_lemma_facts(session, lemma.id) == []


def test_unknown_fact_type_is_rejected(session: Session) -> None:
    lemma = _noun(session)

    assert add_lemma_fact(session, lemma.id, "no_such_fact", "true") is None
    assert validate_lemma_fact("no_such_fact", "true") is not None
    assert validate_lemma_fact("quantifiable", "true") is None


def test_delete(session: Session) -> None:
    lemma = _noun(session)
    add_lemma_fact(session, lemma.id, "quantifiable", "true")

    assert delete_lemma_fact(session, lemma.id, "quantifiable") is True
    assert delete_lemma_fact(session, lemma.id, "quantifiable") is False
    assert get_quantifiable(session, lemma.id) is None


def test_facts_are_removed_with_their_lemma(session: Session) -> None:
    lemma = _noun(session)
    add_lemma_fact(session, lemma.id, "quantifiable", "true")

    session.delete(lemma)
    session.commit()

    assert session.query(LemmaFact).count() == 0


def test_numeral_accepts_digits_only() -> None:
    assert validate_lemma_fact("numeral", "1") is None
    assert validate_lemma_fact("numeral", "1000000") is None
    assert validate_lemma_fact("numeral", "one") is not None
    assert validate_lemma_fact("numeral", "1,000") is not None
    assert validate_lemma_fact("numeral", "") is not None
    assert validate_lemma_fact("numeral", None) is not None


def test_numeral_is_stored_on_a_numeral_lemma(session: Session) -> None:
    lemma = Lemma(
        guid="Z01_002",
        lemma_text="one",
        definition_text="The cardinal number 1.",
        pos_type="numeral",
        pos_subtype="cardinal",
        difficulty_level=4,
    )
    session.add(lemma)
    session.commit()

    assert add_lemma_fact(session, lemma.id, "numeral", "1") is not None
    assert add_lemma_fact(session, lemma.id, "numeral", "one") is None
    assert get_lemma_fact_value(session, lemma.id, "numeral") == "1"
