"""Tests for the Phase 1 structural Element interfaces."""

from __future__ import annotations

from typing import Iterator, Sequence

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.conversation import add_conversation, add_conversation_sentence
from storage.crud.lemma import add_lemma
from storage.crud.name_entity import create_name, set_name_translation
from storage.crud.phrase import add_phrase, set_phrase_translation
from storage.crud.sentence import add_sentence
from storage.crud.sentence_translation import add_sentence_translation
from storage.elements.interfaces import (
    CompositeElement,
    Element,
    ElementRef,
    GuidElement,
    LanguageValue,
    LanguageValueElement,
    LeveledElement,
    MultiwordElement,
    VerifiableElement,
    WordElement,
)
from storage.models.concept import Concept, SubConcept
from storage.models.schema import Base


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _element_identity(element: Element) -> tuple[str, str]:
    """Exercise the smallest interface without knowing the concrete model."""
    return element.element_type, element.display_text


def _word_text(element: WordElement) -> str:
    return element.word_text


def _expression_text(element: MultiwordElement) -> str:
    return element.expression_text


def _guid(element: GuidElement) -> str | None:
    return element.guid


def _verified(element: VerifiableElement) -> bool:
    return element.verified


def _level(element: LeveledElement) -> int | None:
    return element.level


def _language_values(element: LanguageValueElement) -> Sequence[LanguageValue]:
    return element.language_values


def _children(element: CompositeElement) -> Sequence[ElementRef]:
    return element.children


def test_lemma_implements_word_and_language_interfaces(session: Session) -> None:
    lemma = add_lemma(
        session,
        lemma_text="light",
        definition_text="visible electromagnetic radiation",
        pos_type="noun",
        difficulty_level=3,
        lithuanian_translation="šviesa",
        verified=True,
        auto_generate_guid=False,
    )
    lemma.guid = "N50_001"
    lemma.disambiguation = "radiation"

    assert _element_identity(lemma) == ("lemma", "light (radiation)")
    assert _word_text(lemma) == "light"
    assert _guid(lemma) == "N50_001"
    assert _verified(lemma) is True
    assert _level(lemma) == 3
    assert _language_values(lemma) == [
        LanguageValue(
            id=lemma.translations[0].id,
            language_code="lt",
            text="šviesa",
            value_kind="headword",
            verified=False,
        )
    ]


def test_phrase_implements_multiword_and_language_interfaces(session: Session) -> None:
    phrase = add_phrase(
        session,
        phrase_subtype="greetings",
        label="Nice to meet you",
        difficulty_level=1,
        verified=True,
    )
    translation = set_phrase_translation(
        session,
        phrase,
        "lt",
        "Malonu susipažinti",
        translation_status="conventional",
        verified=True,
    )

    assert _element_identity(phrase) == ("phrase", "Nice to meet you")
    assert _expression_text(phrase) == "Nice to meet you"
    assert _guid(phrase) == "F01_001"
    assert _verified(phrase) is True
    assert _level(phrase) == 1
    assert _language_values(phrase) == [
        LanguageValue(
            id=translation.id,
            language_code="lt",
            text="Malonu susipažinti",
            value_kind="translation",
            verified=True,
            status="conventional",
        )
    ]


def test_name_is_an_element_with_renderings(session: Session) -> None:
    name = create_name(
        session,
        name_text="Fresh Mart",
        kind="organization",
        disambiguation="the grocery store",
        verified=True,
    )
    rendering = set_name_translation(
        session,
        name,
        language_code="lt",
        translation="Fresh Mart",
        verified=True,
    )

    assert _element_identity(name) == ("name", "Fresh Mart (the grocery store)")
    assert _verified(name) is True
    assert _language_values(name) == [
        LanguageValue(
            id=rendering.id,
            language_code="lt",
            text="Fresh Mart",
            value_kind="transliteration",
            verified=True,
        )
    ]
    assert not hasattr(name, "word_text")


def test_sentence_prefers_english_display_and_exposes_versions(session: Session) -> None:
    sentence = add_sentence(session, verified=True)
    sentence.minimum_level = 2
    lithuanian = add_sentence_translation(session, sentence, "lt", "Šuo žaidžia.")
    english = add_sentence_translation(session, sentence, "en", "The dog plays.", verified=True)

    assert _element_identity(sentence) == ("sentence", "The dog plays.")
    assert _guid(sentence) == "S_00001"
    assert _verified(sentence) is True
    assert _level(sentence) == 2
    assert _language_values(sentence) == [
        LanguageValue(
            id=english.id,
            language_code="en",
            text="The dog plays.",
            value_kind="version",
            verified=True,
        ),
        LanguageValue(
            id=lithuanian.id,
            language_code="lt",
            text="Šuo žaidžia.",
            value_kind="version",
            verified=False,
        ),
    ]
    assert not hasattr(sentence, "expression_text")


def test_sentence_display_has_stable_fallbacks(session: Session) -> None:
    translated = add_sentence(session)
    add_sentence_translation(session, translated, "lt", "Šuo žaidžia.")
    untranslated = add_sentence(session)

    assert translated.display_text == "Šuo žaidžia."
    assert untranslated.display_text == untranslated.guid


def test_conversation_is_a_sorted_sentence_composite(session: Session) -> None:
    conversation = add_conversation(session, title="At the park", verified=True)
    conversation.minimum_level = 4
    first_sentence = add_sentence(session)
    second_sentence = add_sentence(session)
    add_conversation_sentence(session, conversation, second_sentence, position=1, speaker="B")
    add_conversation_sentence(session, conversation, first_sentence, position=0, speaker="A")

    assert _element_identity(conversation) == ("conversation", "At the park")
    assert _verified(conversation) is True
    assert _level(conversation) == 4
    assert _children(conversation) == [
        ElementRef("sentence", first_sentence.id),
        ElementRef("sentence", second_sentence.id),
    ]


def test_concept_implements_only_the_common_verified_view(session: Session) -> None:
    concept = Concept(slug="War_of_1812", verified=True)
    session.add(concept)
    session.flush()

    assert _element_identity(concept) == ("concept", "War of 1812")
    assert _verified(concept) is True
    assert not hasattr(concept, "guid")
    assert not hasattr(concept, "language_values")


def test_lemma_projects_definition_and_disambiguation(session: Session) -> None:
    """Per-language definition and sense disambiguation reach the projection.

    They are gloss and qualifier rather than status/status_note: those describe
    the value, while the status pair records workflow state.
    """
    lemma = add_lemma(
        session,
        lemma_text="light",
        definition_text="visible electromagnetic radiation",
        pos_type="noun",
        lithuanian_translation="šviesa",
        auto_generate_guid=False,
    )
    translation = lemma.translations[0]
    translation.definition_text = "elektromagnetinė spinduliuotė"
    translation.disambiguation = "radiation"
    translation.translation_status = "needs_review"
    session.flush()

    (value,) = _language_values(lemma)
    assert value.gloss == "elektromagnetinė spinduliuotė"
    assert value.qualifier == "radiation"
    assert value.status == "needs_review"
    assert value.status_note is None


def test_language_value_gloss_and_qualifier_default_to_absent(session: Session) -> None:
    """A type without them projects None rather than an empty string.

    Phrases have neither, and that is a property of the type rather than an
    unfilled field, so consumers can render the column as "not applicable".
    """
    phrase = add_phrase(
        session,
        phrase_subtype="greetings",
        label="good morning",
    )
    set_phrase_translation(session, phrase, "lt", "labas rytas")
    session.flush()

    (value,) = _language_values(phrase)
    assert value.gloss is None
    assert value.qualifier is None


def test_sub_concept_implements_the_common_verified_view(session: Session) -> None:
    sub_concept = SubConcept(
        slug="Sicilian_Defense",
        category="chess_concept",
        verified=False,
    )
    session.add(sub_concept)
    session.flush()

    assert _element_identity(sub_concept) == ("sub_concept", "Sicilian Defense")
    assert _verified(sub_concept) is False
