"""Bulk generation preserves the scalar builder's data and transaction behavior."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.crud.grammar_fact import add_grammar_fact
from storage.models.grammar_fact import GrammarFact
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation, WordToken
from storage.models.variant_form import VariantForm
from words.mechanical_forms import generate_for_session, generate_lemma_forms


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def noun(session: Session, word: str, guid: str) -> Lemma:
    lemma = Lemma(lemma_text=word, guid=guid, pos_type="noun", definition_text=word)
    session.add(lemma)
    session.flush()
    add_grammar_fact(session, lemma.id, "en", "countability", "countable")
    return lemma


def test_shared_tokens_irregular_forms_and_logs_survive_batches(session: Session) -> None:
    first = noun(session, "child", "N99_001")
    second = noun(session, "child", "N99_002")
    for lemma in (first, second):
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                language_code="en",
                grammatical_form="noun/en_plural",
                derivative_form_text="children",
                ipa_pronunciation="/ˈtʃɪldrən/",
                verified=True,
            )
        )
    session.commit()
    counts = generate_for_session(session, languages=["en"], batch_size=1)
    forms = session.query(DerivativeForm).all()
    assert len(forms) == 8
    assert session.query(WordToken).count() == 3
    assert {row.derivative_form_text for row in forms} == {
        "child",
        "children",
        "child's",
        "children's",
    }
    plurals = [row for row in forms if row.grammatical_form == "noun/en_plural"]
    assert all(row.ipa_pronunciation == "/ˈtʃɪldrən/" and row.verified for row in plurals)
    assert len({row.word_token_id for row in forms if row.derivative_form_text == "child"}) == 1
    logs = session.query(OperationLog).all()
    assert len(logs) == 2
    assert all(json.loads(row.fact)["forms_added"] == 3 for row in logs)
    assert counts["en"]["forms_added"] == 6
    assert generate_for_session(session, languages=["en"], batch_size=1)["en"]["forms_added"] == 0
    assert session.query(OperationLog).count() == 2


def test_inherited_number_facts_and_independent_dialect_translations(session: Session) -> None:
    lemma = noun(session, "pants", "N99_003")
    session.add_all(
        [
            LemmaTranslation(lemma_id=lemma.id, language_code="es", translation="pantalones"),
            LemmaTranslation(lemma_id=lemma.id, language_code="es-419", translation="gafas"),
        ]
    )
    add_grammar_fact(session, lemma.id, "es", "number_type", "plurale_tantum")
    session.commit()
    generate_lemma_forms(session, lemma, "es-419")
    session.commit()
    scalar = {
        (row.grammatical_form, row.derivative_form_text)
        for row in session.query(DerivativeForm).all()
    }
    session.query(DerivativeForm).delete()
    session.commit()
    generate_for_session(session, languages=["es-419"], batch_size=1)
    assert {
        (row.grammatical_form, row.derivative_form_text)
        for row in session.query(DerivativeForm).all()
    } == scalar
    assert scalar == {("noun/es-419_plural", "gafas"), ("noun/es-419_singular", "gafas")}


def test_variants_have_separate_paradigms_and_keep_pronunciations(session: Session) -> None:
    lemma = noun(session, "donut", "N99_004")
    session.add_all(
        [
            VariantForm(
                lemma_id=lemma.id,
                language_code="en",
                variant_kind="spelling",
                variant_key="doughnut",
                variant_form_text="doughnut",
                grammatical_form="noun/en_singular",
                is_base_form=True,
            ),
            VariantForm(
                lemma_id=lemma.id,
                language_code="en",
                variant_kind="spelling",
                variant_key="doughnut",
                variant_form_text="doughnuts",
                grammatical_form="noun/en_plural",
                ipa_pronunciation="/test/",
            ),
        ]
    )
    session.commit()
    generate_for_session(session, languages=["en"], batch_size=1)
    variants = session.query(VariantForm).all()
    assert {row.variant_form_text for row in variants} == {
        "doughnut",
        "doughnuts",
        "doughnut's",
        "doughnuts'",
    }
    assert (
        next(row for row in variants if row.variant_form_text == "doughnuts").ipa_pronunciation
        == "/test/"
    )
    assert not any(
        row.derivative_form_text.startswith("doughnut") for row in session.query(DerivativeForm)
    )


def test_dry_run_leaves_no_snapshot_or_writes(session: Session) -> None:
    noun(session, "book", "N99_005")
    session.commit()
    assert (
        generate_for_session(session, languages=["en"], batch_size=1, dry_run=True)["en"][
            "forms_added"
        ]
        == 4
    )
    assert session.query(DerivativeForm).count() == 0
    assert session.query(WordToken).count() == 0
    assert session.query(OperationLog).count() == 0
    assert "mechanical_inputs" not in session.info
    assert "mechanical_batch" not in session.info


def test_queries_scale_with_batches_instead_of_forms(session: Session) -> None:
    for index in range(100):
        noun(session, "book", f"N99_{index:03}")
    session.commit()
    executions: list[str] = []

    def record(
        connection: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        executions.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        counts = generate_for_session(session, languages=["en"], batch_size=100)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert counts["en"]["forms_added"] == 400
    assert len(executions) < 30
    assert session.query(GrammarFact).count() == 100


def test_derived_facts_clear_uncertainty_without_overwriting_empty_facts(session: Session) -> None:
    from storage.crud.uncertain_llm_result import record_uncertain_llm_result
    from storage.models.uncertain_llm_result import UncertainLLMResult

    fresh = noun(session, "library", "N99_010")
    empty = noun(session, "library", "N99_011")
    for lemma in (fresh, empty):
        session.add(
            LemmaTranslation(lemma_id=lemma.id, language_code="lt", translation="biblioteka")
        )
        record_uncertain_llm_result(
            session, "grammatical_gender", "lt", "uncertain", lemma_id=lemma.id
        )
    session.add(
        GrammarFact(
            lemma_id=empty.id, language_code="lt", fact_type="grammatical_gender", fact_value=None
        )
    )
    session.commit()
    generate_for_session(session, languages=["lt"], batch_size=2)
    facts = {
        row.lemma_id: row.fact_value
        for row in session.query(GrammarFact).filter(
            GrammarFact.language_code == "lt", GrammarFact.fact_type == "grammatical_gender"
        )
    }
    assert facts == {fresh.id: "feminine", empty.id: None}
    assert session.query(UncertainLLMResult).count() == 0
