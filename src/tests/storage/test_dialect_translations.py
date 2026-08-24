"""Storage behaviour for dialect language codes (zh-tw, es-419, pt-br, es-mx).

A dialect is an ordinary language code once registered, so the point of these
tests is the two places where it is *not* ordinary: the sort key it inherits
from its parent, and audio that is filed under a code other than the one the
text is stored under.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview, Base, Lemma, LemmaTranslation
from storage.translation_helpers import (
    compute_sort_key,
    get_translation,
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


def _stored(session: Session, lemma: Lemma, language_code: str) -> LemmaTranslation:
    return (
        session.query(LemmaTranslation)
        .filter(
            LemmaTranslation.lemma_id == lemma.id,
            LemmaTranslation.language_code == language_code,
        )
        .one()
    )


def _add_audio(session: Session, language_code: str, expected_text: str) -> AudioQualityReview:
    review = AudioQualityReview(
        guid="N01_001",
        language_code=language_code,
        voice_name="nova",
        filename=f"N01_001_{language_code}.mp3",
        expected_text=expected_text,
        manifest_md5="0" * 32,
        status="approved",
    )
    session.add(review)
    session.commit()
    return review


def test_dialect_translation_gets_its_parents_sort_key(session: Session, lemma: Lemma) -> None:
    """es-419 sorts with the Spanish letter remapping, not with no key at all."""
    assert has_sort_key("es-419")

    set_translation(session, lemma, "es-419", "ñandú")
    session.commit()

    assert _stored(session, lemma, "es-419").sort_key == compute_sort_key("es", "ñandú")


def test_updating_a_dialect_translation_refreshes_its_sort_key(
    session: Session, lemma: Lemma
) -> None:
    """The update path used to skip dialects, leaving a stale key behind."""
    set_translation(session, lemma, "es-419", "carro")
    session.commit()
    set_translation(session, lemma, "es-419", "ñandú")
    session.commit()

    assert _stored(session, lemma, "es-419").sort_key == compute_sort_key("es", "ñandú")


def test_dialect_translations_are_stored_apart_from_their_parent(
    session: Session, lemma: Lemma
) -> None:
    """The whole point of a storage dialect: two rows, two answers.

    Overlap between the two is expected and stored in full rather than
    resolved at read time, so a release file carries both words even when they
    are the same word.
    """
    set_translation(session, lemma, "pt", "carro")
    set_translation(session, lemma, "pt-br", "automóvel")
    session.commit()

    assert get_translation(session, lemma, "pt") == "carro"
    assert get_translation(session, lemma, "pt-br") == "automóvel"


def test_identical_text_in_both_varieties_is_stored_twice(session: Session, lemma: Lemma) -> None:
    """The common case: es and es-419 agree, and both rows say so."""
    set_translation(session, lemma, "es", "libro")
    set_translation(session, lemma, "es-419", "libro")
    session.commit()

    assert get_translation(session, lemma, "es") == "libro"
    assert get_translation(session, lemma, "es-419") == "libro"


def test_changing_a_translation_invalidates_its_own_audio(session: Session, lemma: Lemma) -> None:
    set_translation(session, lemma, "es-419", "carro")
    session.commit()
    review = _add_audio(session, "es-419", "carro")

    set_translation(session, lemma, "es-419", "auto")
    session.commit()

    assert review.status == "needs_replacement"


def test_changing_a_translation_invalidates_the_audio_of_dialects_reading_it(
    session: Session, lemma: Lemma
) -> None:
    """es-mx audio speaks es-419's words, so it goes stale with them.

    It is filed under language_code "es-mx", which a filter on the changed
    code alone would miss -- leaving a recording that claims an expected_text
    nothing says any more.
    """
    set_translation(session, lemma, "es-419", "carro")
    session.commit()
    mexican = _add_audio(session, "es-mx", "carro")

    set_translation(session, lemma, "es-419", "auto")
    session.commit()

    assert mexican.status == "needs_replacement"


def test_changing_the_parent_does_not_invalidate_the_dialects_audio(
    session: Session, lemma: Lemma
) -> None:
    """es and es-419 are separate words; a Castilian edit is not a Mexican one."""
    set_translation(session, lemma, "es", "coche")
    set_translation(session, lemma, "es-419", "carro")
    session.commit()
    mexican = _add_audio(session, "es-mx", "carro")

    set_translation(session, lemma, "es", "automóvil")
    session.commit()

    assert mexican.status == "approved"
