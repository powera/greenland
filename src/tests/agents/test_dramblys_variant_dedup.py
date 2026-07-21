"""Tests for alternate-spelling awareness in Dramblys word intake.

Word lists mix spellings freely -- one will offer "gray" and another "grey" --
so both intake gates have to recognize a spelling variant as an existing word:

  * ``check_wordlist_coverage`` decides whether a word is missing and should be
    staged as a pending import at all.
  * ``_find_duplicate_lemma`` is the last gate before a pending import becomes
    a real lemma.

Without variant awareness "grey" reads as a new word at both gates and ends up
as a duplicate concept alongside "gray".
"""

from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from agents.dramblys.staging import _find_duplicate_lemma
from agents.dramblys.wordlist import check_wordlist_coverage, get_existing_english_words
from storage.models import Base, DerivativeForm, Lemma
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'variant_dedup.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()

    lemma = Lemma(
        lemma_text="gray",
        definition_text="Of a color between black and white.",
        pos_type="adjective",
        pos_subtype="color",
        guid="A02_008",
    )
    db_session.add(lemma)
    db_session.flush()

    db_session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            language_code="en",
            grammatical_form="adjective/en_positive",
            derivative_form_text="gray",
            is_base_form=True,
        )
    )
    for grammatical_form, text in [
        ("adjective/en_positive", "grey"),
        ("adjective/en_comparative", "greyer"),
    ]:
        db_session.add(
            VariantForm(
                lemma_id=lemma.id,
                language_code="en",
                variant_kind=VARIANT_KIND_SPELLING,
                variant_key="grey",
                grammatical_form=grammatical_form,
                variant_form_text=text,
                is_base_form=(grammatical_form == "adjective/en_positive"),
            )
        )
    db_session.commit()

    yield db_session
    db_session.close()


def test_existing_words_include_variant_spellings(session: Session) -> None:
    """Variant spellings count as words the database already has."""
    words = get_existing_english_words(session, ["gray", "grey", "greyer", "magenta"])
    assert "gray" in words
    assert "grey" in words
    assert "greyer" in words
    assert "magenta" not in words


def test_wordlist_coverage_treats_variant_as_present(session: Session, tmp_path: Path) -> None:
    """A wordlist offering "grey" is covered by the existing "gray" lemma."""
    wordlist = tmp_path / "colors.txt"
    wordlist.write_text("[[grey]]\n[[magenta]]\n", encoding="utf-8")

    coverage = check_wordlist_coverage(str(wordlist), session)

    assert "grey" not in coverage["missing_words"]
    assert "magenta" in coverage["missing_words"]
    assert coverage["in_database"] == 1


def test_find_duplicate_lemma_matches_variant_spelling(session: Session) -> None:
    """Approving a pending "grey" resolves to the existing "gray" lemma."""
    duplicate = _find_duplicate_lemma(session, "grey", "adjective", "color")
    assert duplicate is not None
    assert duplicate.lemma_text == "gray"


def test_find_duplicate_lemma_still_matches_lemma_text(session: Session) -> None:
    """The direct lemma-text match is unaffected by the variant lookup."""
    duplicate = _find_duplicate_lemma(session, "gray", "adjective", "color")
    assert duplicate is not None
    assert duplicate.lemma_text == "gray"


def test_find_duplicate_lemma_respects_pos_filters(session: Session) -> None:
    """A variant match still has to agree on part of speech."""
    assert _find_duplicate_lemma(session, "grey", "noun", None) is None


def test_find_duplicate_lemma_returns_none_for_new_word(session: Session) -> None:
    """An unrelated word is not spuriously matched to a variant."""
    assert _find_duplicate_lemma(session, "magenta", "adjective", "color") is None
