"""Characterization tests for the element-interface refactor boundary.

These tests intentionally exercise today's public CRUD behavior without adding
``Element`` protocols. They provide the Phase 0 safety net described in
``docs/element_types_design.md`` for lemmas, phrases, sentences, and names.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.crud.lemma import add_lemma, get_lemma_by_guid
from storage.crud.name_entity import (
    create_name,
    get_name_by_id,
    get_name_translation,
    set_name_translation,
)
from storage.crud.phrase import add_phrase, get_phrase_by_id, set_phrase_translation
from storage.crud.sentence import add_sentence, get_sentence_by_id
from storage.crud.sentence_translation import (
    add_sentence_translation,
    delete_sentence_translation,
    get_or_create_sentence_translation,
    get_sentence_translation,
    update_sentence_translation,
)
from storage.models.name_entity import Name
from storage.models.schema import Base, Lemma, Phrase, PhraseTranslation, Sentence


@pytest.fixture()
def session() -> Iterator[Session]:
    """Provide a complete, isolated storage schema for each characterization."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def test_missing_ids_and_guids_return_none(session: Session) -> None:
    """Each existing lookup uses ``None`` for a missing element."""
    assert get_lemma_by_guid(session, "N02_999") is None
    assert get_phrase_by_id(session, 999) is None
    assert get_sentence_by_id(session, 999) is None
    assert get_name_by_id(session, 999) is None


def test_current_display_fields_remain_type_specific(session: Session) -> None:
    """Pin the values that a future Element projection will expose."""
    lemma = add_lemma(
        session,
        lemma_text="light",
        definition_text="visible electromagnetic radiation",
        pos_type="noun",
        auto_generate_guid=False,
    )
    phrase = add_phrase(session, "greetings", "Nice to meet you")
    sentence = add_sentence(session, pattern_type="SVO")
    english_sentence = add_sentence_translation(session, sentence, "en", "The dog plays.")
    name = create_name(
        session,
        name_text="George",
        kind="given_name",
        disambiguation="the neighbor",
    )

    assert lemma.lemma_text == "light"
    assert phrase.label == "Nice to meet you"
    assert english_sentence.translation_text == "The dog plays."
    assert name.display_text == "George (the neighbor)"


def test_phrase_translation_upsert_keeps_one_row_per_language(session: Session) -> None:
    phrase = add_phrase(session, "greetings", "Hello")
    first = set_phrase_translation(
        session,
        phrase,
        "lt",
        "labas",
        translation_status="near_equivalent",
        translation_status_note="informal",
        verified=True,
    )
    updated = set_phrase_translation(
        session,
        phrase,
        "lt",
        "sveiki",
        translation_status="conventional",
        translation_status_note="plural or polite",
        verified=True,
    )

    rows = session.query(PhraseTranslation).filter_by(phrase_id=phrase.id).all()
    assert updated.id == first.id
    assert len(rows) == 1
    assert rows[0].translation == "sveiki"
    assert rows[0].translation_status == "conventional"
    assert rows[0].translation_status_note == "plural or polite"
    assert rows[0].verified is True


def test_name_rendering_upsert_keeps_one_row_per_language(session: Session) -> None:
    name = create_name(session, name_text="George", kind="given_name")
    first = set_name_translation(
        session,
        name,
        language_code="lt",
        translation="Džordžas",
        phonetic_pronunciation="JOR-jus",
        verified=True,
    )
    updated = set_name_translation(
        session,
        name,
        language_code="lt",
        translation="Georgas",
        phonetic_pronunciation="GEOR-gas",
        verified=True,
    )

    rendering = get_name_translation(session, name, "lt")
    assert rendering is not None
    assert updated.id == first.id == rendering.id
    assert len(name.translations) == 1
    assert rendering.translation == "Georgas"
    assert rendering.phonetic_pronunciation == "GEOR-gas"
    assert rendering.verified is True


def test_sentence_translation_rejects_a_second_row_for_language(session: Session) -> None:
    """Sentences enforce uniqueness rather than treating add as an upsert."""
    sentence = add_sentence(session)
    add_sentence_translation(session, sentence, "en", "The dog plays.")

    with pytest.raises(IntegrityError):
        add_sentence_translation(session, sentence, "en", "A dog plays.")


def test_sentence_get_or_create_does_not_overwrite_existing_text(session: Session) -> None:
    sentence = add_sentence(session)
    original, created = get_or_create_sentence_translation(
        session, sentence, "en", "The dog plays.", verified=True
    )
    found, created_again = get_or_create_sentence_translation(
        session, sentence, "en", "Replacement text", verified=False
    )

    assert created is True
    assert created_again is False
    assert found.id == original.id
    assert found.translation_text == "The dog plays."
    assert found.verified is True


def test_sentence_translation_update_preserves_omitted_verification(session: Session) -> None:
    sentence = add_sentence(session)
    translation = add_sentence_translation(session, sentence, "en", "The dog plays.", verified=True)

    update_sentence_translation(session, translation, translation_text="The dog is playing.")

    assert translation.translation_text == "The dog is playing."
    assert translation.verified is True


def test_sentence_translation_delete_is_deferred_until_flush(session: Session) -> None:
    sentence = add_sentence(session)
    translation = add_sentence_translation(session, sentence, "en", "The dog plays.")
    delete_sentence_translation(session, translation)

    assert translation in session.deleted
    session.flush()
    assert get_sentence_translation(session, sentence.id, "en") is None


@pytest.mark.parametrize("element_kind", ["lemma", "phrase", "sentence", "name"])
def test_create_helpers_do_not_commit(session: Session, element_kind: str) -> None:
    """Creation helpers flush for ids but leave transaction ownership to callers."""
    created: Any
    model: type[Any]
    if element_kind == "lemma":
        created = add_lemma(
            session,
            lemma_text="book",
            definition_text="a written work",
            pos_type="noun",
            auto_generate_guid=False,
        )
        model = Lemma
    elif element_kind == "phrase":
        created = add_phrase(session, "greetings", "Good morning")
        model = Phrase
    elif element_kind == "sentence":
        created = add_sentence(session, pattern_type="SVO")
        model = Sentence
    else:
        created = create_name(session, name_text="George", kind="given_name")
        model = Name

    created_id = created.id
    assert created_id is not None
    assert session.in_transaction()

    session.rollback()

    assert session.get(model, created_id) is None
