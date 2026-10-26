"""Tests for the shared sentence-level rule in storage.crud.sentence."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import constants
import storage.models  # noqa: F401
from storage.crud.sentence import (
    CONTEXT_WORD_MIN_LEMMAS,
    EXAMPLE_SENTENCE_COLLECTION,
    calculate_minimum_level,
    sentence_level_from_word_levels,
    sentence_word_levels,
)
from storage.integrity.sentences import check_sentence_levels
from storage.models.schema import Base, Lemma, Sentence, SentenceWord, SentenceWordHint


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _lemma(guid: str, level: int) -> Lemma:
    return Lemma(
        guid=guid,
        lemma_text=guid.lower(),
        definition_text=f"definition for {guid}",
        pos_type="noun",
        difficulty_level=level,
    )


def _hint(sentence: Sentence, lemma: Lemma, position: int) -> SentenceWordHint:
    return SentenceWordHint(
        sentence_id=sentence.id,
        lemma_id=lemma.id,
        position=position,
        slot_name="noun",
        english_text=lemma.lemma_text,
    )


def test_short_sentence_uses_hardest_word() -> None:
    assert CONTEXT_WORD_MIN_LEMMAS == 3
    assert sentence_level_from_word_levels([30, 2]) == 30


def test_longer_sentence_uses_second_hardest_word() -> None:
    assert sentence_level_from_word_levels([1, 190, 5]) == 5


def test_no_words_has_no_level() -> None:
    assert sentence_level_from_word_levels([]) is None


def test_word_levels_dedupe_lemmas_across_languages(session: Session) -> None:
    hard = _lemma("N01_001", 50)
    easy = _lemma("N01_002", 2)
    sentence = Sentence(guid="S_00001")
    session.add_all([hard, easy, sentence])
    session.flush()
    for language_code in ("en", "lt"):
        for position, lemma in enumerate((hard, easy)):
            session.add(
                SentenceWord(
                    sentence_id=sentence.id,
                    language_code=language_code,
                    position=position,
                    part_of_speech="noun",
                    lemma_id=lemma.id,
                )
            )
    session.flush()

    # Two lemmas, not four rows: the hardest word still sets the level.
    assert sorted(sentence_word_levels(session, sentence.id)) == [2, 50]
    assert calculate_minimum_level(session, sentence) == 50


def test_word_levels_fall_back_to_hints_and_rank_excluded_last(session: Session) -> None:
    excluded = _lemma("N01_001", constants.EXCLUDE_DIFFICULTY_LEVEL)
    easy = _lemma("N01_002", 3)
    other = _lemma("N01_003", 4)
    sentence = Sentence(guid="S_00001")
    session.add_all([excluded, easy, other, sentence])
    session.flush()
    session.add_all(
        [_hint(sentence, lemma, position) for position, lemma in enumerate((excluded, easy, other))]
    )
    session.flush()

    assert max(sentence_word_levels(session, sentence.id)) == constants.MAX_DIFFICULTY_LEVEL + 1
    # Three lemmas: the excluded word is the one understood from context.
    assert calculate_minimum_level(session, sentence) == 4


def test_integrity_check_leaves_word_examples_unlevelled(session: Session) -> None:
    lemma = _lemma("N01_001", 5)
    example = Sentence(guid="S_00001", sentence_collection=EXAMPLE_SENTENCE_COLLECTION)
    lesson = Sentence(guid="S_00002")
    session.add_all([lemma, example, lesson])
    session.flush()
    session.add_all([_hint(example, lemma, 0), _hint(lesson, lemma, 0)])
    session.flush()

    result = check_sentence_levels(session, fix=True)

    assert result["fixed_count"] == 1
    assert example.minimum_level is None
    assert lesson.minimum_level == 5
