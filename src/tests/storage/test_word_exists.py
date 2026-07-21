"""Tests for the canonical "does this English word already exist?" check.

``word_exists_in_english`` and ``filter_existing_english_words`` answer the same
question -- one word at a time, or a batch in a fixed number of queries -- and
the two must never disagree. Three hand-rolled copies of this logic previously
did: only one knew about variant spellings, so "grey" was treated as known when
checking a wordlist but staged as a missing word by the frequency check.

A word counts as existing if it is a lemma, the base of a disambiguated lemma,
an English derivative form, or an English variant spelling. The exclusions list
is opt-in, because import gates and coverage measurements want opposite answers
for an excluded word.
"""

from pathlib import Path
from typing import Generator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models import Base, DerivativeForm, Lemma
from storage.models.imports import WordExclusion
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm
from storage.queries.lemma import filter_existing_english_words, word_exists_in_english


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'word_exists.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()

    # "gray": a plain lemma, with an English derivative form and the British
    # spelling "grey" as a variant paradigm.
    gray = Lemma(
        lemma_text="gray",
        definition_text="Of a color between black and white.",
        pos_type="adjective",
        pos_subtype="color",
        guid="A02_008",
    )
    # "light (color)": a disambiguated lemma, so a bare "light" is covered.
    light = Lemma(
        lemma_text="light (color)",
        definition_text="Pale in color.",
        pos_type="adjective",
        pos_subtype="color",
        guid="A02_009",
    )
    db_session.add_all([gray, light])
    db_session.flush()

    db_session.add(
        DerivativeForm(
            lemma_id=gray.id,
            language_code="en",
            grammatical_form="adjective/en_comparative",
            derivative_form_text="grayer",
            is_base_form=False,
        )
    )
    # A non-English form must not answer for an English word.
    db_session.add(
        DerivativeForm(
            lemma_id=gray.id,
            language_code="lt",
            grammatical_form="adjective/lt_positive",
            derivative_form_text="pilkas",
            is_base_form=True,
        )
    )
    db_session.add(
        VariantForm(
            lemma_id=gray.id,
            language_code="en",
            variant_kind=VARIANT_KIND_SPELLING,
            variant_key="grey",
            grammatical_form="adjective/en_positive",
            variant_form_text="grey",
            is_base_form=True,
        )
    )
    db_session.add(
        WordExclusion(
            excluded_word="thier",
            language_code="en",
            exclusion_reason="misspelling",
        )
    )
    db_session.commit()

    yield db_session
    db_session.close()


EXISTING_WORDS: List[str] = [
    "gray",  # lemma
    "grayer",  # English derivative form
    "grey",  # English variant spelling
    "light",  # base of the disambiguated "light (color)"
    "light (color)",  # the disambiguated lemma itself
]

ABSENT_WORDS: List[str] = [
    "magenta",  # simply not present
    "pilkas",  # a form, but Lithuanian -- not an English word
    "thier",  # excluded, which only counts when asked for
    "gra",  # prefix of a real lemma, not a word
    "lighthouse",  # shares a prefix with "light (color)"
]


@pytest.mark.parametrize("word", EXISTING_WORDS)
def test_word_exists(session: Session, word: str) -> None:
    """Every form a word can take counts as the word existing."""
    assert word_exists_in_english(session, word) is True


@pytest.mark.parametrize("word", ABSENT_WORDS)
def test_word_absent(session: Session, word: str) -> None:
    """Words with no entry in any form are absent."""
    assert word_exists_in_english(session, word) is False


def test_lookup_is_case_and_whitespace_insensitive(session: Session) -> None:
    """Callers pass words straight from corpora and files, so input is untidy."""
    assert word_exists_in_english(session, "GRAY") is True
    assert word_exists_in_english(session, "  Grey  ") is True


def test_empty_word_is_absent(session: Session) -> None:
    """A blank entry is not a word, and must not match every row."""
    assert word_exists_in_english(session, "") is False
    assert word_exists_in_english(session, "   ") is False


def test_exclusions_are_opt_in(session: Session) -> None:
    """An excluded word is absent for coverage, present for an import gate.

    Coverage asks "is this in the dictionary?" -- an excluded word is not.
    An import gate asks "should I propose this?" -- an excluded word was
    already rejected once, so it should not come back.
    """
    assert word_exists_in_english(session, "thier") is False
    assert word_exists_in_english(session, "thier", include_exclusions=True) is True


def test_batch_matches_single_word_check(session: Session) -> None:
    """The batch form must agree with the per-word form on every word."""
    candidates = EXISTING_WORDS + ABSENT_WORDS
    found = filter_existing_english_words(session, candidates)

    for word in candidates:
        expected = word_exists_in_english(session, word)
        assert (word.lower() in found) is expected, f"disagreement on {word!r}"


def test_batch_returns_only_existing_words(session: Session) -> None:
    """Absent words are omitted rather than reported."""
    found = filter_existing_english_words(session, ["gray", "grey", "magenta", "light"])
    assert found == {"gray", "grey", "light"}


def test_batch_honors_exclusions_flag(session: Session) -> None:
    """The batch form gates exclusions the same way the per-word form does."""
    assert filter_existing_english_words(session, ["thier"]) == set()
    assert filter_existing_english_words(session, ["thier"], include_exclusions=True) == {"thier"}


def test_batch_normalizes_input(session: Session) -> None:
    """Batch input gets the same case/whitespace treatment, and dedupes."""
    found = filter_existing_english_words(session, ["GRAY", "  gray ", "Grey", ""])
    assert found == {"gray", "grey"}


def test_batch_on_empty_input(session: Session) -> None:
    """An empty batch asks nothing of the database."""
    assert filter_existing_english_words(session, []) == set()


def test_batch_exceeds_sqlite_variable_limit(session: Session) -> None:
    """Batches are chunked, so a batch past SQLite's ~999-variable cap works.

    The frequency check runs thousands of candidates through this in one call;
    without chunking SQLite raises "too many SQL variables".
    """
    candidates = [f"filler{n}" for n in range(1500)] + ["gray", "grey"]
    found = filter_existing_english_words(session, candidates)
    assert found == {"gray", "grey"}
