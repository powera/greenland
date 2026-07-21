"""Tests for routing LLM alternate spellings into variant_forms.

A spelling variant is the same lexeme as its lemma, so "grey" must not be
stored as a synonym-class DerivativeForm alongside "large"/"huge". It goes to
variant_forms with its own paradigm; see storage.models.variant_form.
"""

from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from langtools.en.variants import build_variant_paradigm
from storage.models import Base, DerivativeForm, Lemma
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from words.synonyms import store_spelling_variants


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'spelling_variants.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    yield db_session
    db_session.close()


def _add_lemma(session: Session, lemma_text: str, pos_type: str) -> Lemma:
    lemma = Lemma(
        lemma_text=lemma_text,
        definition_text=f"Definition of {lemma_text}.",
        pos_type=pos_type,
    )
    session.add(lemma)
    session.flush()
    return lemma


def test_spelling_variant_is_not_stored_as_a_synonym(session: Session) -> None:
    """The whole point of the reroute: no synonym-class DerivativeForm row."""
    lemma = _add_lemma(session, "gray", "adjective")

    stored = store_spelling_variants(session, lemma, "en", ["grey"])

    assert stored == 1
    assert session.query(DerivativeForm).count() == 0
    assert session.query(VariantForm).count() > 0


def test_spelling_variant_is_expanded_to_a_full_paradigm(session: Session) -> None:
    """ "grey" carries its own comparative and superlative."""
    lemma = _add_lemma(session, "gray", "adjective")

    store_spelling_variants(session, lemma, "en", ["grey"])

    rows = session.query(VariantForm).all()
    by_form = {row.grammatical_form: row.variant_form_text for row in rows}
    assert by_form == {
        "adjective/en_positive": "grey",
        "adjective/en_comparative": "greyer",
        "adjective/en_superlative": "greyest",
    }
    assert all(row.variant_key == "grey" for row in rows)
    assert all(row.variant_kind == VARIANT_KIND_SPELLING for row in rows)

    # is_base_form is scoped to the variant: "grey" is the base form of the
    # "grey" paradigm, and only that row carries the flag.
    base_forms = [row.grammatical_form for row in rows if row.is_base_form]
    assert base_forms == ["adjective/en_positive"]


def test_unexpandable_variant_still_stores_its_base_form(session: Session) -> None:
    """An irregular lemma's variant is stored bare rather than dropped.

    The paradigm is left for a human, but the spelling still has to be present
    or duplicate detection stops recognizing it.
    """
    lemma = _add_lemma(session, "good", "adjective")

    stored = store_spelling_variants(session, lemma, "en", ["goud"])

    assert stored == 1
    rows = session.query(VariantForm).all()
    assert len(rows) == 1
    assert rows[0].variant_form_text == "goud"
    assert rows[0].grammatical_form == "adjective/en_positive"
    assert rows[0].is_base_form is True


def test_variant_paradigm_refuses_irregular_lemmas() -> None:
    """Irregular forms are spelled for the lemma; no rule respells them."""
    assert build_variant_paradigm("good", "goud", "adjective") is None
    assert build_variant_paradigm("go", "goe", "verb") is None


def test_variant_paradigm_expands_regular_lemmas() -> None:
    assert build_variant_paradigm("gray", "grey", "adjective") == {
        "positive": "grey",
        "comparative": "greyer",
        "superlative": "greyest",
    }
    assert build_variant_paradigm("doughnut", "donut", "noun") == {
        "singular": "donut",
        "plural": "donuts",
    }
