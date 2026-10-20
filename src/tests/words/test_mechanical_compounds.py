"""The shared writer must reach safe language-specific compound builders."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, Lemma
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import DerivativeForm
from storage.translation_helpers import set_translation
from words.mechanical_forms import generate_lemma_forms


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


@pytest.mark.parametrize(
    "text,plural,override",
    [
        ("teléfono móvil", "teléfonos móviles", True),
        ("ropa interior", "ropas interiores", True),
        ("dedo del pie", "dedos del pie", False),
        ("parque de bomberos", "parques de bomberos", False),
        ("carne de res", "carnes de res", False),
    ],
)
def test_spanish_compound_plural_is_persisted(
    session: Session, text: str, plural: str, override: bool
) -> None:
    lemma = Lemma(lemma_text="test noun", pos_type="noun", definition_text="A test sense")
    session.add(lemma)
    session.flush()
    set_translation(session, lemma, "es", text)
    if override:
        session.add(
            GrammarFact(
                lemma_id=lemma.id, language_code="es", fact_type="plural", fact_value=plural
            )
        )
        session.flush()
    assert generate_lemma_forms(session, lemma, "es")["forms_added"] == 2
    stored_plural = (
        session.query(DerivativeForm)
        .filter_by(lemma_id=lemma.id, grammatical_form="noun/es_plural")
        .one()
    )
    assert stored_plural.derivative_form_text == plural
    assert generate_lemma_forms(session, lemma, "es")["forms_added"] == 0


@pytest.mark.parametrize(
    "language,second_plural", [("es", "estáis de pie"), ("es-419", "están de pie")]
)
def test_stand_conjugates_estar_and_preserves_the_phrase(
    session: Session, language: str, second_plural: str
) -> None:
    lemma = Lemma(lemma_text="stand", pos_type="verb", definition_text="Be upright")
    session.add(lemma)
    session.flush()
    set_translation(session, lemma, language, "estar de pie")
    assert generate_lemma_forms(session, lemma, language)["forms_added"] > 0
    forms = {
        row.grammatical_form: row.derivative_form_text
        for row in session.query(DerivativeForm).filter_by(lemma_id=lemma.id)
    }
    assert forms[f"verb/{language}_1s_present"] == "estoy de pie"
    assert forms[f"verb/{language}_2p_present"] == second_plural


@pytest.mark.parametrize(
    "language,text,pos",
    [
        ("lt", "mobilusis telefonas", "noun"),
        ("es", "ser / estar", "verb"),
        ("es", "padre/madre", "noun"),
        ("es", "dar un paseo", "verb"),
    ],
)
def test_unhandled_phrases_are_still_declined(
    session: Session, language: str, text: str, pos: str
) -> None:
    lemma = Lemma(lemma_text="test", pos_type=pos, definition_text="A test sense")
    session.add(lemma)
    session.flush()
    set_translation(session, lemma, language, text)
    assert generate_lemma_forms(session, lemma, language)["forms_added"] == 0
