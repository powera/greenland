"""Every lemma-creating path writes the ``en`` translation row from lemma_text."""

from typing import Any, Dict, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401 -- register every model before create_all
from storage.crud.lemma import add_lemma
from storage.models.schema import Base, Lemma, LemmaTranslation
from storage.release.lemma import import_release_record
from storage.translation_helpers import ensure_english_translation


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _english_row(session: Session, lemma: Lemma) -> Optional[str]:
    row = (
        session.query(LemmaTranslation)
        .filter(LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == "en")
        .one_or_none()
    )
    return row.translation if row is not None else None


def _flushed_lemma(session: Session, text: str = "ethambutol") -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text="an antibiotic for tuberculosis",
        pos_type="noun",
        pos_subtype="medication_remedy",
    )
    session.add(lemma)
    session.flush()
    return lemma


def test_ensure_writes_the_row_from_lemma_text() -> None:
    session = _make_session()
    lemma = _flushed_lemma(session)

    assert ensure_english_translation(session, lemma) is True
    assert _english_row(session, lemma) == "ethambutol"


def test_ensure_leaves_an_existing_row_alone() -> None:
    session = _make_session()
    lemma = _flushed_lemma(session, "New York City")
    session.add(LemmaTranslation(lemma_id=lemma.id, language_code="en", translation="New York"))
    session.flush()

    assert ensure_english_translation(session, lemma) is False
    assert _english_row(session, lemma) == "New York"
    assert session.query(LemmaTranslation).filter_by(language_code="en").count() == 1


def test_ensure_needs_a_flushed_lemma() -> None:
    session = _make_session()
    lemma = Lemma(lemma_text="x", definition_text="x", pos_type="noun")

    with pytest.raises(ValueError):
        ensure_english_translation(session, lemma)


def test_add_lemma_writes_the_english_row() -> None:
    session = _make_session()

    lemma = add_lemma(
        session,
        lemma_text="insulin",
        definition_text="a hormone that regulates blood sugar",
        pos_type="noun",
        pos_subtype="medication_remedy",
    )

    assert _english_row(session, lemma) == "insulin"


def test_release_record_import_writes_the_english_row() -> None:
    session = _make_session()
    record: Dict[str, Any] = {
        "guid": "N64_010",
        "pos_type": "noun",
        "pos_subtype": "celestial_object",
        "concept_label": "Andromeda (constellation)",
        "concept_definition": "a constellation in the northern sky",
        "translations": {"en": "Andromeda", "fr": "Andromède"},
        "disambiguation": {"en": "constellation"},
        "difficulty_level": 1055,
    }

    lemma = import_release_record(session, record)

    assert _english_row(session, lemma) == "Andromeda"
    fr = session.query(LemmaTranslation).filter_by(lemma_id=lemma.id, language_code="fr").one()
    assert fr.translation == "Andromède"
