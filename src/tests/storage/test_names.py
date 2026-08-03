"""Tests for the names registry (Name / NameTranslation).

Names are the third kind of entry beside lemmas and concepts; these tests pin
the properties that make them distinct: the closed kind vocabulary, the
(text, kind) uniqueness that lets a scene reuse a character, per-language
renderings, and the sentence-word link that is mutually exclusive with a lemma.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.name_entity import (
    count_names,
    create_name,
    delete_name,
    find_name,
    get_name_renderings,
    get_name_translation,
    get_or_create_name,
    list_names,
    set_name_translation,
    update_name,
)
from storage.crud.sentence import add_sentence
from storage.crud.sentence_word import add_sentence_word
from storage.models.name_entity import (
    NAME_KIND_LABELS,
    NAME_KINDS,
    Name,
    is_valid_name_kind,
    normalize_name_text,
)
from storage.models.schema import Base, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def test_every_kind_has_a_label() -> None:
    """The UI reads labels by kind, so the two vocabularies must not drift."""
    assert set(NAME_KIND_LABELS) == set(NAME_KINDS)
    assert all(is_valid_name_kind(kind) for kind in NAME_KINDS)
    assert not is_valid_name_kind("not_a_kind")


def test_normalize_name_text_collapses_whitespace() -> None:
    assert normalize_name_text("  George  ") == "George"
    assert normalize_name_text("Mr.   Chen") == "Mr. Chen"


def test_normalize_name_text_preserves_case() -> None:
    """Case matters: "Mark" the name must not fold into "mark" the lemma."""
    assert normalize_name_text("Mark") == "Mark"


def test_create_name_rejects_unknown_kind(session: Session) -> None:
    with pytest.raises(ValueError, match="Unknown name kind"):
        create_name(session, name_text="George", kind="protagonist")


def test_create_name_rejects_unknown_gender(session: Session) -> None:
    with pytest.raises(ValueError, match="Unknown gender"):
        create_name(session, name_text="George", kind="given_name", gender="male")


def test_create_name_rejects_empty_text(session: Session) -> None:
    with pytest.raises(ValueError, match="non-empty text"):
        create_name(session, name_text="   ", kind="given_name")


def test_find_name_normalizes_lookup(session: Session) -> None:
    create_name(session, name_text="George", kind="given_name")
    session.commit()

    assert find_name(session, "  George ") is not None
    assert find_name(session, "George", kind="given_name") is not None
    assert find_name(session, "George", kind="place") is None


def test_get_or_create_name_reuses_the_same_character(session: Session) -> None:
    """Casting a name twice must reuse the row, or renderings would fork."""
    first, created_first = get_or_create_name(
        session, name_text="George", kind="given_name", gender="masculine"
    )
    second, created_second = get_or_create_name(session, name_text="George", kind="given_name")
    session.commit()

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert count_names(session) == 1


def test_get_or_create_name_fills_a_missing_gender_only(session: Session) -> None:
    """A gender learned later fills a blank, but never overwrites a curated one."""
    name, _ = get_or_create_name(session, name_text="Robin", kind="given_name")
    assert name.gender is None

    get_or_create_name(session, name_text="Robin", kind="given_name", gender="neutral")
    assert name.gender == "neutral"

    get_or_create_name(session, name_text="Robin", kind="given_name", gender="feminine")
    assert name.gender == "neutral"


def test_same_text_different_kind_are_separate_names(session: Session) -> None:
    """ "Chen" the family name and "Chen" the shop are different entries."""
    create_name(session, name_text="Chen", kind="family_name")
    create_name(session, name_text="Chen", kind="organization")
    session.commit()

    assert count_names(session) == 2
    assert count_names(session, kind="organization") == 1


def test_set_name_translation_creates_then_updates(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")

    set_name_translation(session, name, language_code="lt", translation="Džordžas")
    set_name_translation(session, name, language_code="zh", translation="乔治")
    session.commit()

    assert get_name_renderings(session, name) == {"lt": "Džordžas", "zh": "乔治"}

    set_name_translation(session, name, language_code="lt", translation="Georgas")
    session.commit()

    rendering = get_name_translation(session, name, "lt")
    assert rendering is not None
    assert rendering.translation == "Georgas"
    assert len(name.translations) == 2


def test_set_name_translation_rejects_empty_rendering(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")
    with pytest.raises(ValueError, match="Empty rendering"):
        set_name_translation(session, name, language_code="lt", translation="   ")


def test_update_name_leaves_omitted_fields_alone(session: Session) -> None:
    name = create_name(
        session, name_text="George", kind="given_name", gender="masculine", notes="the shopper"
    )

    update_name(session, name, verified=True)
    session.commit()

    assert name.verified is True
    assert name.gender == "masculine"
    assert name.notes == "the shopper"


def test_delete_name_removes_its_renderings(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")
    set_name_translation(session, name, language_code="lt", translation="Džordžas")
    session.commit()

    delete_name(session, name)
    session.commit()

    assert count_names(session) == 0
    assert session.query(Name).count() == 0


def test_list_names_filters_and_sorts(session: Session) -> None:
    create_name(session, name_text="Maria", kind="given_name")
    create_name(session, name_text="George", kind="given_name")
    create_name(session, name_text="Fresh Mart", kind="organization")
    session.commit()

    assert [name.name_text for name in list_names(session)] == [
        "Fresh Mart",
        "George",
        "Maria",
    ]
    assert [name.name_text for name in list_names(session, kind="organization")] == ["Fresh Mart"]
    assert [name.name_text for name in list_names(session, search="mar")] == [
        "Fresh Mart",
        "Maria",
    ]


def test_sentence_word_links_to_a_name(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")
    sentence = add_sentence(session, pattern_type="conversation")

    word = add_sentence_word(
        session,
        sentence=sentence,
        position=0,
        part_of_speech="name",
        language_code="en",
        name=name,
        english_text="George",
    )
    session.commit()

    assert word.name_id == name.id
    assert word.lemma_id is None
    assert word.name is not None
    assert word.name.name_text == "George"


def test_sentence_word_refuses_both_a_lemma_and_a_name(session: Session) -> None:
    """A token is vocabulary or it is a name; storing both would double-count it."""
    name = create_name(session, name_text="Rose", kind="given_name")
    lemma = Lemma(lemma_text="rose", definition_text="a flower", pos_type="noun")
    session.add(lemma)
    session.flush()
    sentence = add_sentence(session, pattern_type="conversation")

    with pytest.raises(ValueError, match="never both"):
        add_sentence_word(
            session,
            sentence=sentence,
            position=0,
            part_of_speech="noun",
            language_code="en",
            lemma=lemma,
            name=name,
        )
