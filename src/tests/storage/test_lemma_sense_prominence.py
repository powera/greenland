"""Tests for the sense_prominence pass-through on storage.crud.lemma.add_lemma.

``Lemma.sense_prominence`` weights the split of a shared spelling's corpus
frequency (see ``wordfreq.lexeme_frequency.get_token_share``). The LLM that
discovers a word already rates it, but the CRUD layer used to have no way to
accept that rating, so every lemma created through ``add_complete_word_entry``
landed on the schema default. These tests cover the parameter, its validation,
and the default when a caller has no opinion.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so every table the log touches is created.
import storage.models  # noqa: F401
from storage.crud.lemma import add_lemma
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_VERY_COMMON,
    Base,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active


def test_defaults_to_common_when_not_given(session: Session) -> None:
    lemma = add_lemma(
        session,
        lemma_text="elephant",
        definition_text="a large mammal",
        pos_type="noun",
        auto_generate_guid=False,
    )

    assert lemma.sense_prominence == SENSE_PROMINENCE_COMMON


def test_stores_an_explicit_rating(session: Session) -> None:
    lemma = add_lemma(
        session,
        lemma_text="top",
        definition_text="a toy that spins on a pointed base",
        pos_type="noun",
        auto_generate_guid=False,
        sense_prominence=SENSE_PROMINENCE_RARE,
    )

    assert lemma.sense_prominence == SENSE_PROMINENCE_RARE


def test_explicit_none_keeps_the_default(session: Session) -> None:
    """A caller with no opinion passes None rather than guessing a label."""
    lemma = add_lemma(
        session,
        lemma_text="elephant",
        definition_text="a large mammal",
        pos_type="noun",
        auto_generate_guid=False,
        sense_prominence=None,
    )

    assert lemma.sense_prominence == SENSE_PROMINENCE_COMMON


def test_unknown_value_is_rejected(session: Session) -> None:
    """An unrecognized label would silently weight as 'common' downstream."""
    with pytest.raises(ValueError, match="sense_prominence"):
        add_lemma(
            session,
            lemma_text="top",
            definition_text="the highest point",
            pos_type="noun",
            auto_generate_guid=False,
            sense_prominence="extremely_common",
        )


def test_existing_lemma_is_returned_unchanged(session: Session) -> None:
    """add_lemma is add-or-get; it must not re-rate a lemma that already exists."""
    first = add_lemma(
        session,
        lemma_text="top",
        definition_text="the highest point",
        pos_type="noun",
        auto_generate_guid=False,
        sense_prominence=SENSE_PROMINENCE_VERY_COMMON,
    )
    second = add_lemma(
        session,
        lemma_text="top",
        definition_text="the highest point",
        pos_type="noun",
        auto_generate_guid=False,
        sense_prominence=SENSE_PROMINENCE_RARE,
    )

    assert second.id == first.id
    assert second.sense_prominence == SENSE_PROMINENCE_VERY_COMMON
