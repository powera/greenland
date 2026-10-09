"""CRUD tests for uncertain_llm_results (questions an LLM was unsure of)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import storage.models  # noqa: F401 -- register every model before create_all
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.crud.lemma import add_lemma
from storage.crud.lemma_fact import add_lemma_fact
from storage.crud.uncertain_llm_result import (
    DEFAULT_MIN_CONFIDENCE,
    GATED_WRITERS,
    LLMQuestion,
    clear_uncertain_llm_result,
    confidence_gated,
    get_uncertain_llm_result,
    record_uncertain_llm_result,
)
from storage.models.schema import Base, Lemma, Sentence
from storage.models.uncertain_llm_result import UncertainLLMResult

_GENDER = "grammatical_gender"
_REPO_ROOT = Path(__file__).resolve().parents[3]


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


# --- confidence_gated ---------------------------------------------------------


def _gated_add(session: Session, lemma: Lemma, value: str | None, **gate: object) -> object:
    return add_grammar_fact(session, lemma.id, "es", _GENDER, value, notes="why", **gate)  # type: ignore[arg-type]


def test_gated_confident_answer_is_written_and_clears(session: Session) -> None:
    lemma = _noun(session)
    record_uncertain_llm_result(session, _GENDER, "es", "low_confidence", lemma_id=lemma.id)
    session.commit()

    fact = _gated_add(session, lemma, "feminine", confidence=0.9, min_confidence=0.8, model="m")

    assert fact is not None
    assert get_grammar_fact_value(session, lemma.id, "es", _GENDER) == "feminine"
    assert not add_grammar_fact.is_uncertain(
        session, lemma_id=lemma.id, language_code="es", fact_type=_GENDER
    )


def test_gated_uncertain_answer_is_recorded_not_written(session: Session) -> None:
    lemma = _noun(session)

    fact = _gated_add(session, lemma, "feminine", confidence=0.6, min_confidence=0.8, model="m")
    session.commit()

    assert fact is None
    assert get_grammar_fact_value(session, lemma.id, "es", _GENDER) is None
    row = get_uncertain_llm_result(session, _GENDER, "es", lemma_id=lemma.id)
    assert row is not None
    assert (row.reason, row.note) == ("low_confidence", "m leaned feminine (0.60): why")
    assert add_grammar_fact.is_uncertain(
        session, lemma_id=lemma.id, language_code="es", fact_type=_GENDER
    )


def test_gated_uses_the_decorator_floor_when_the_call_gives_none(session: Session) -> None:
    lemma = _noun(session)

    assert _gated_add(session, lemma, "feminine", confidence=DEFAULT_MIN_CONFIDENCE - 0.01) is None
    assert get_uncertain_llm_result(session, _GENDER, "es", lemma_id=lemma.id) is not None


def test_gated_empty_answer_writes_and_records_nothing(session: Session) -> None:
    lemma = _noun(session)

    assert _gated_add(session, lemma, None, confidence=0.2, model="m") is None
    assert session.query(UncertainLLMResult).count() == 0


def test_ungated_call_is_the_plain_writer(session: Session) -> None:
    lemma = _noun(session)

    assert _gated_add(session, lemma, "masculine") is not None
    assert get_grammar_fact_value(session, lemma.id, "es", _GENDER) == "masculine"


def test_gated_lemma_fact_has_no_language(session: Session) -> None:
    lemma = _noun(session)

    stored = add_lemma_fact(
        session, lemma.id, "has_individual_instances", "true", confidence=0.5, model="m"
    )

    assert stored is None
    assert get_uncertain_llm_result(session, "has_individual_instances", None, lemma_id=lemma.id)


def test_a_writer_without_the_gate_parameters_cannot_be_gated() -> None:
    def writer(session: Session, value: str) -> None:
        return None

    with pytest.raises(TypeError, match="confidence"):
        confidence_gated(question=lambda a: LLMQuestion("t"), value="value")(writer)


# Modules that store LLM answers.  A gated writer called there without
# confidence= is an unchecked write of a model's answer.
_LLM_ANSWER_MODULES = (
    "src/words/grammar_fact_generation.py",
    "src/words/grammar_facts.py",
    "src/words/lemma_fact_generation.py",
    "src/words/grammar_fact_tasks/english_principal_parts.py",
    "src/workqueue/handlers/words/grammar_facts.py",
    "src/words/lemma_creation.py",
    "src/words/pronunciation.py",
    "src/words/pronunciation_generation.py",
    "src/workqueue/handlers/words/pronunciations.py",
    "src/wordfreq/translation/generate_forms_base.py",
    "src/workqueue/handlers/words/forms.py",
    "src/words/translation_populate.py",
    "src/sentences/translation.py",
)


@pytest.mark.parametrize("path", _LLM_ANSWER_MODULES)
def test_llm_code_passes_a_confidence_to_gated_writers(path: str) -> None:
    import storage.crud.grammar_fact  # noqa: F401 -- register the gated writers
    import storage.crud.lemma_fact  # noqa: F401
    import storage.crud.sentence_translation  # noqa: F401
    import words.grammar_fact_tasks.english_principal_parts  # noqa: F401
    import words.lemma_creation  # noqa: F401
    import words.pronunciation_generation  # noqa: F401
    import wordfreq.translation.generate_forms_base  # noqa: F401

    tree = ast.parse((_REPO_ROOT / path).read_text())
    unchecked = [
        f"{path}:{node.lineno} {node.func.id}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in GATED_WRITERS
        and not any(keyword.arg == "confidence" for keyword in node.keywords)
    ]
    assert unchecked == []
