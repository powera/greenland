"""Tests for the lemma <-> concept pairing CRUD (storage.crud.concept).

The pairing stores the concept's Wikidata Q-id directly on the lemma side (no
hard FK to the concepts table) so it survives the hosted deployment where
concepts live in a separate read-only database. These tests cover the strict
one-to-one behavior and the Q-id readout used by the data/release export.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Import the full model registry so the lemmas table (FK target) is created too.
import storage.models  # noqa: F401
from storage.crud.concept import (
    get_lemma_for_qid,
    get_link_for_lemma,
    get_link_for_qid,
    get_qid_for_lemma,
    link_lemma_to_concept,
    unlink_lemma_from_concept,
)
from storage.models.schema import Base, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _make_lemma(db: Session, text: str) -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text=f"{text}.", pos_type="noun")
    db.add(lemma)
    db.commit()
    return lemma


def test_link_normalizes_qid_and_reads_back(session: Session) -> None:
    lemma = _make_lemma(session, "apple")
    assert get_qid_for_lemma(session, lemma.id) is None

    link = link_lemma_to_concept(session, lemma.id, "q89", concept_slug="Apple", verified=True)

    assert link is not None
    assert link.qid == "Q89"
    assert link.concept_slug == "Apple"
    assert get_qid_for_lemma(session, lemma.id) == "Q89"
    qid_link = get_link_for_qid(session, "Q89")
    assert qid_link is not None
    assert qid_link.lemma_id == lemma.id


def test_get_lemma_for_qid_round_trips(session: Session) -> None:
    lemma = _make_lemma(session, "apple")
    # Unpaired and invalid Q-ids both read back as None.
    assert get_lemma_for_qid(session, "Q89") is None
    assert get_lemma_for_qid(session, "not-a-qid") is None

    link_lemma_to_concept(session, lemma.id, "Q89")

    # Reverse lookup returns the lemma, accepting any casing for the Q-id.
    found = get_lemma_for_qid(session, "q89")
    assert found is not None
    assert found.id == lemma.id
    assert found.lemma_text == "apple"


def test_invalid_qid_is_rejected(session: Session) -> None:
    lemma = _make_lemma(session, "apple")
    assert link_lemma_to_concept(session, lemma.id, "not-a-qid") is None
    assert get_link_for_lemma(session, lemma.id) is None


def test_one_to_one_on_both_sides(session: Session) -> None:
    apple = _make_lemma(session, "apple")
    pear = _make_lemma(session, "pear")
    assert link_lemma_to_concept(session, apple.id, "Q89") is not None

    # A lemma already linked cannot be relinked to a different concept.
    assert link_lemma_to_concept(session, apple.id, "Q90") is None
    # A concept already linked cannot be relinked to a different lemma.
    assert link_lemma_to_concept(session, pear.id, "Q89") is None


def test_relinking_same_pair_updates_metadata(session: Session) -> None:
    lemma = _make_lemma(session, "apple")
    link_lemma_to_concept(session, lemma.id, "Q89", verified=False)

    updated = link_lemma_to_concept(
        session, lemma.id, "q89", concept_slug="Apple", verified=True, notes="curated"
    )

    assert updated is not None
    assert updated.verified is True
    assert updated.concept_slug == "Apple"
    assert updated.notes == "curated"


def test_unlink_removes_pairing(session: Session) -> None:
    lemma = _make_lemma(session, "apple")
    link_lemma_to_concept(session, lemma.id, "Q89")

    assert unlink_lemma_from_concept(session, lemma_id=lemma.id) is True
    assert get_qid_for_lemma(session, lemma.id) is None
    # Unlinking an unlinked lemma is a no-op.
    assert unlink_lemma_from_concept(session, lemma_id=lemma.id) is False
