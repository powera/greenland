"""Storage behaviour for dialect language codes (zh-tw, es-419, pt-br).

A dialect is a language code like any other once it is registered, so the point
of these tests is the places where it is *not* like any other: the sort key it
inherits from its parent, and reads that fall back to the parent's text when
the dialect itself has none.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, Lemma
from storage.translation_helpers import (
    compute_sort_key,
    get_translation,
    get_translation_with_dialect_fallback,
    has_sort_key,
    set_translation,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def lemma(session: Session) -> Lemma:
    entry = Lemma(
        lemma_text="car",
        definition_text="A road vehicle with an engine and four wheels.",
        pos_type="noun",
        guid="N01_001",
    )
    session.add(entry)
    session.commit()
    return entry


def test_dialect_translation_gets_its_parents_sort_key(session: Session, lemma: Lemma) -> None:
    """es-419 sorts with the Spanish letter remapping, not with no key at all."""
    assert has_sort_key("es-419")

    set_translation(session, lemma, "es-419", "carro")
    session.commit()

    assert compute_sort_key("es-419", "ñandú") == compute_sort_key("es", "ñandú")


def test_updating_a_dialect_translation_refreshes_its_sort_key(
    session: Session, lemma: Lemma
) -> None:
    """The update path used to skip dialects, leaving a stale key behind."""
    from storage.models.schema import LemmaTranslation

    set_translation(session, lemma, "es-419", "carro")
    session.commit()
    set_translation(session, lemma, "es-419", "ñandú")
    session.commit()

    stored = (
        session.query(LemmaTranslation)
        .filter(
            LemmaTranslation.lemma_id == lemma.id,
            LemmaTranslation.language_code == "es-419",
        )
        .one()
    )
    assert stored.sort_key == compute_sort_key("es", "ñandú")


def test_fallback_prefers_the_dialects_own_translation(session: Session, lemma: Lemma) -> None:
    set_translation(session, lemma, "es", "coche")
    set_translation(session, lemma, "es-419", "carro")
    session.commit()

    text, source = get_translation_with_dialect_fallback(session, lemma, "es-419")

    assert (text, source) == ("carro", "es-419")


def test_fallback_uses_the_parent_when_the_dialect_is_empty(session: Session, lemma: Lemma) -> None:
    set_translation(session, lemma, "pt", "carro")
    session.commit()

    text, source = get_translation_with_dialect_fallback(session, lemma, "pt-br")

    assert (text, source) == ("carro", "pt")


def test_fallback_reports_nothing_when_neither_variety_has_text(
    session: Session, lemma: Lemma
) -> None:
    assert get_translation_with_dialect_fallback(session, lemma, "es-419") == (None, None)


def test_a_presentation_dialect_reads_the_variety_that_covers_it(
    session: Session, lemma: Lemma
) -> None:
    """es-mx has no rows of its own; it reads es-419's."""
    set_translation(session, lemma, "es", "coche")
    set_translation(session, lemma, "es-419", "carro")
    session.commit()

    text, source = get_translation_with_dialect_fallback(session, lemma, "es-mx")

    assert (text, source) == ("carro", "es-419")


def test_a_plain_language_needs_no_fallback(session: Session, lemma: Lemma) -> None:
    set_translation(session, lemma, "de", "Auto")
    session.commit()

    assert get_translation_with_dialect_fallback(session, lemma, "de") == ("Auto", "de")


def test_dialect_translations_are_stored_apart_from_their_parent(
    session: Session, lemma: Lemma
) -> None:
    """The whole point of a storage dialect: two rows, two answers."""
    set_translation(session, lemma, "pt", "carro")
    set_translation(session, lemma, "pt-br", "automóvel")
    session.commit()

    assert get_translation(session, lemma, "pt") == "carro"
    assert get_translation(session, lemma, "pt-br") == "automóvel"
