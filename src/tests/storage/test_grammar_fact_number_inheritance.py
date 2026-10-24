"""Spanish regional number paradigms inherit without duplicating storage rows."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from langtools.es.mechanical import build_paradigm
from storage.crud.grammar_fact import (
    add_grammar_fact,
    bulk_get_effective_grammar_facts,
    get_grammar_fact_value,
)
from storage.models import Base, Lemma
from storage.models.grammar_fact import GrammarFact


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active
    engine.dispose()


@pytest.mark.parametrize("regional_value", [None, "", "singulare_tantum"])
def test_number_inheritance_and_explicit_override(
    session: Session, regional_value: str | None
) -> None:
    lemma = Lemma(lemma_text="glasses", definition_text="eyewear", pos_type="noun")
    session.add(lemma)
    session.flush()
    add_grammar_fact(session, lemma.id, "es", "number_type", "plurale_tantum")
    add_grammar_fact(session, lemma.id, "es", "grammatical_gender", "feminine")
    add_grammar_fact(session, lemma.id, "es", "plural", "gafas")
    if regional_value is not None:
        add_grammar_fact(session, lemma.id, "es-419", "number_type", regional_value)
    expected = regional_value or "plurale_tantum"
    before = session.query(GrammarFact).count()

    assert get_grammar_fact_value(session, lemma.id, "es-419", "number_type") == expected
    assert bulk_get_effective_grammar_facts(session, [lemma.id], "es-419") == {
        lemma.id: {"number_type": expected}
    }
    # The spelling differs from Peninsular gafas; number behavior still applies.
    forms, _ = build_paradigm(session, lemma, "noun", "es-419", "anteojos")
    assert forms == (
        {"singular": "anteojos"}
        if regional_value == "singulare_tantum"
        else {"singular": "anteojos", "plural": "anteojos"}
    )
    assert get_grammar_fact_value(session, lemma.id, "es-419", "plural") is None
    assert get_grammar_fact_value(session, lemma.id, "es-419", "grammatical_gender") is None
    assert get_grammar_fact_value(session, lemma.id, "pt-br", "number_type") is None
    assert session.query(GrammarFact).count() == before


def test_missing_spanish_number_stays_unknown(session: Session) -> None:
    assert get_grammar_fact_value(session, 999, "es-419", "number_type") is None
    assert bulk_get_effective_grammar_facts(session, [999], "es-419") == {}
