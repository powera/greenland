"""CRUD tests for uncertain_llm_results (questions an LLM was unsure of)."""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import storage.models  # noqa: F401 -- register every model before create_all
from storage.crud.grammar_fact import add_grammar_fact
from storage.crud.lemma import add_lemma
from storage.crud.uncertain_llm_result import (
    clear_uncertain_llm_result,
    get_uncertain_llm_result,
    record_uncertain_llm_result,
)
from storage.models.schema import Base, Lemma, Sentence
from storage.models.uncertain_llm_result import UncertainLLMResult

_GENDER = "grammatical_gender"


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def _noun(session: Session, text: str = "radio") -> Lemma:
    return add_lemma(
        session,
        lemma_text=text,
        definition_text=f"a {text}",
        pos_type="noun",
        auto_generate_guid=False,
    )


def _sentence(session: Session) -> Sentence:
    sentence = Sentence()
    session.add(sentence)
    session.commit()
    return sentence


def test_record_and_read_back(session: Session) -> None:
    lemma = _noun(session)

    record_uncertain_llm_result(
        session, _GENDER, "es", "low_confidence", "leaned feminine (0.5)", lemma_id=lemma.id
    )
    session.commit()

    row = get_uncertain_llm_result(session, _GENDER, "es", lemma_id=lemma.id)
    assert row is not None
    assert (row.reason, row.note) == ("low_confidence", "leaned feminine (0.5)")
    assert get_uncertain_llm_result(session, _GENDER, "es-419", lemma_id=lemma.id) is None


def test_recording_again_replaces_the_row(session: Session) -> None:
    lemma = _noun(session)

    record_uncertain_llm_result(
        session, _GENDER, "es", "low_confidence", "first", lemma_id=lemma.id
    )
    record_uncertain_llm_result(
        session, _GENDER, "es", "low_confidence", "second", lemma_id=lemma.id
    )
    session.commit()

    assert session.query(UncertainLLMResult).count() == 1
    row = get_uncertain_llm_result(session, _GENDER, "es", lemma_id=lemma.id)
    assert row is not None and row.note == "second"


def test_language_independent_question(session: Session) -> None:
    lemma = _noun(session)

    record_uncertain_llm_result(
        session, "has_individual_instances", None, "low_confidence", lemma_id=lemma.id
    )
    session.commit()

    assert get_uncertain_llm_result(session, "has_individual_instances", None, lemma_id=lemma.id)
    assert (
        get_uncertain_llm_result(session, "has_individual_instances", "en", lemma_id=lemma.id)
        is None
    )


def test_sentence_question(session: Session) -> None:
    sentence = _sentence(session)

    record_uncertain_llm_result(
        session, "translation", "lt", "low_confidence", sentence_id=sentence.id
    )
    session.commit()

    assert get_uncertain_llm_result(session, "translation", "lt", sentence_id=sentence.id)
    assert clear_uncertain_llm_result(session, "translation", "lt", sentence_id=sentence.id)
    assert get_uncertain_llm_result(session, "translation", "lt", sentence_id=sentence.id) is None


def test_exactly_one_target_is_required(session: Session) -> None:
    lemma = _noun(session)
    sentence = _sentence(session)

    with pytest.raises(ValueError):
        get_uncertain_llm_result(session, _GENDER, "es")
    with pytest.raises(ValueError):
        get_uncertain_llm_result(session, _GENDER, "es", lemma_id=lemma.id, sentence_id=sentence.id)

    session.add(
        UncertainLLMResult(
            lemma_id=lemma.id,
            sentence_id=sentence.id,
            topic=_GENDER,
            reason="low_confidence",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_unique_per_question_even_with_null_language(session: Session) -> None:
    lemma = _noun(session)
    for _ in range(2):
        session.add(
            UncertainLLMResult(
                lemma_id=lemma.id,
                language_code=None,
                topic="has_individual_instances",
                reason="low_confidence",
            )
        )
    with pytest.raises(IntegrityError):
        session.flush()


def test_storing_the_fact_clears_the_uncertainty(session: Session) -> None:
    lemma = _noun(session)
    record_uncertain_llm_result(session, _GENDER, "es", "low_confidence", lemma_id=lemma.id)
    record_uncertain_llm_result(session, _GENDER, "es-419", "low_confidence", lemma_id=lemma.id)
    session.commit()

    add_grammar_fact(session, lemma.id, "es", _GENDER, "feminine")

    assert get_uncertain_llm_result(session, _GENDER, "es", lemma_id=lemma.id) is None
    assert get_uncertain_llm_result(session, _GENDER, "es-419", lemma_id=lemma.id) is not None


def test_deleting_the_lemma_deletes_its_rows(session: Session) -> None:
    lemma = _noun(session)
    record_uncertain_llm_result(session, _GENDER, "es", "low_confidence", lemma_id=lemma.id)
    session.commit()

    session.delete(lemma)
    session.commit()

    assert session.query(UncertainLLMResult).count() == 0
