"""Tests for the database-derived proper-noun vocabulary whitelist."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, DerivativeForm, Lemma
from wordfreq.corpora.proper_noun_vocabulary import (
    VOCABULARY_NAME_SUBTYPES,
    excluded_words,
    load_always_vocabulary,
    load_always_vocabulary_by_subtype,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(
    session: Session,
    lemma_text: str,
    subtype: str,
    forms: Sequence[str] = (),
    pos_type: str = "noun",
    language_code: str = "en",
) -> None:
    """Add one lemma with the given subtype and surface forms."""
    lemma = Lemma(
        lemma_text=lemma_text,
        definition_text=lemma_text,
        pos_type=pos_type,
        pos_subtype=subtype,
    )
    session.add(lemma)
    session.flush()
    for form_text in forms:
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text=form_text,
                language_code=language_code,
                grammatical_form="noun/en_singular",
            )
        )
    session.flush()


def test_days_and_months_are_kept_as_vocabulary() -> None:
    """The words the capitalization filter would otherwise eat."""
    session = _make_session()
    for name in ("Monday", "Saturday", "January"):
        _add_lemma(session, name, "temporal_name", [name])

    words = load_always_vocabulary(session, subtypes=["temporal_name"])
    assert words == ("january", "monday", "saturday")


def test_ambiguous_month_names_are_held_back() -> None:
    """ "May" as a whitelist entry would credit the month with the modal verb."""
    session = _make_session()
    for name in ("March", "May", "Saturday"):
        _add_lemma(session, name, "temporal_name", [name])

    words = load_always_vocabulary(session, subtypes=["temporal_name"])
    assert words == ("saturday",)

    held = excluded_words(session, subtypes=["temporal_name"])
    assert set(held) == {"march", "may"}


def test_multiword_names_are_kept_whole() -> None:
    """Splitting "New York" would whitelist "new" -- an ordinary English word."""
    session = _make_session()
    _add_lemma(session, "New York", "city", ["New York"])
    _add_lemma(session, "Los Angeles", "city", ["Los Angeles"])

    words = load_always_vocabulary(session, subtypes=["city"])
    assert words == ("los angeles", "new york")
    for fragment in ("new", "york", "los", "angeles"):
        assert fragment not in words


def test_lowercase_entries_are_skipped() -> None:
    """An uncapitalized entry is never filtered as a name, so it is a no-op."""
    session = _make_session()
    _add_lemma(session, "Warsaw", "city", ["Warsaw"])
    _add_lemma(session, "area", "city", ["area"])

    words = load_always_vocabulary(session, subtypes=["city"])
    assert words == ("warsaw",)


def test_inflected_forms_are_all_collected() -> None:
    """Every English form of a name enters, not just the headword."""
    session = _make_session()
    _add_lemma(session, "Alps", "geographic_place", ["Alps", "Alp"])

    words = load_always_vocabulary(session, subtypes=["geographic_place"])
    assert words == ("alp", "alps")


def test_headword_without_forms_is_collected() -> None:
    """A lemma need not have any DerivativeForm rows to be whitelisted."""
    session = _make_session()
    _add_lemma(session, "Europe", "region")

    assert load_always_vocabulary(session, subtypes=["region"]) == ("europe",)


def test_other_languages_and_parts_of_speech_are_ignored() -> None:
    """Only English forms of noun lemmas are read."""
    session = _make_session()
    _add_lemma(session, "Paris", "city", ["Paryžius"], language_code="lt")
    _add_lemma(session, "Polish", "city", ["Polish"], pos_type="adjective")

    assert load_always_vocabulary(session, subtypes=["city"]) == ("paris",)


def test_by_subtype_keeps_categories_apart() -> None:
    session = _make_session()
    _add_lemma(session, "Saturday", "temporal_name", ["Saturday"])
    _add_lemma(session, "Warsaw", "city", ["Warsaw"])

    by_subtype = load_always_vocabulary_by_subtype(session, subtypes=["temporal_name", "city"])
    assert by_subtype == {"temporal_name": ("saturday",), "city": ("warsaw",)}


def test_place_name_is_not_a_default_subtype() -> None:
    """``place_name`` holds common nouns (area, city), not capitalized names."""
    assert "place_name" not in VOCABULARY_NAME_SUBTYPES
    assert "temporal_name" in VOCABULARY_NAME_SUBTYPES
    assert "region" in VOCABULARY_NAME_SUBTYPES
    assert "country" not in VOCABULARY_NAME_SUBTYPES
