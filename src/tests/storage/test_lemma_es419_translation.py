"""Tests for the es-419 pass-through from the word-import path to LemmaTranslation.

``DEFINITIONS_PROMPT_LANGUAGES`` has asked the LLM for Latin American Spanish
alongside lt/es/fr/zh for a while, but ``word_processing.process_word`` built
its ``TranslationSet`` from only four of the five and dropped the es-419 answer
on the floor, so a word created through the pending-import approval path got no
es-419 row. These tests cover the parameter on the two CRUD layers it crosses
and the mapping to the right language code.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.crud.derivative_form import add_complete_word_entry
from storage.crud.lemma import add_lemma
from storage.models.schema import Base, LemmaTranslation
from storage.models.translations import Translation, TranslationSet


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def _translations(session: Session, lemma_id: int) -> dict[str, str]:
    rows = session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id == lemma_id).all()
    return {row.language_code: row.translation for row in rows}


def test_add_lemma_stores_es419_under_its_own_code(session: Session) -> None:
    """es-419 is a storage dialect, so it gets a row of its own, not es's."""
    lemma = add_lemma(
        session=session,
        lemma_text="car",
        definition_text="A road vehicle with four wheels.",
        pos_type="noun",
        spanish_translation="coche",
        spanish_latam_translation="carro",
    )
    session.flush()

    stored = _translations(session, lemma.id)
    assert stored["es-419"] == "carro"
    # The Peninsular row is untouched: overlap between the two is stored, not
    # resolved, so both varieties keep their own word.
    assert stored["es"] == "coche"


def test_add_lemma_omits_es419_when_not_given(session: Session) -> None:
    """A blank means "not generated yet", so no empty row is written for it."""
    lemma = add_lemma(
        session=session,
        lemma_text="bagel",
        definition_text="A ring-shaped bread roll.",
        pos_type="noun",
        spanish_translation="bagel",
    )
    session.flush()

    assert "es-419" not in _translations(session, lemma.id)


def test_add_complete_word_entry_carries_es419_from_translation_set(session: Session) -> None:
    """The TranslationSet route is what process_word uses; it must not drop es-419."""
    form = add_complete_word_entry(
        session=session,
        token="computer",
        lemma_text="computer",
        definition_text="An electronic device for processing data.",
        pos_type="noun",
        grammatical_form="singular",
        translations=TranslationSet(
            spanish=Translation(text="ordenador"),
            spanish_latam=Translation(text="computadora"),
        ),
    )
    session.flush()

    stored = _translations(session, form.lemma_id)
    assert stored["es-419"] == "computadora"
    assert stored["es"] == "ordenador"
