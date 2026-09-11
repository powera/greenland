"""Tests for shared curriculum bounds and derived sentence levels."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import constants
import storage.models  # noqa: F401
from storage.integrity.lemmas import check_invalid_difficulty_levels
from storage.integrity.sentences import check_sentence_levels
from storage.crud.difficulty_override import add_difficulty_override
from storage.models.schema import Base, Lemma, Sentence, SentenceWordHint


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


def test_valid_levels_include_general_and_topic_bands_and_exclusion(
    session: Session,
) -> None:
    session.add_all(
        [
            _lemma("N01_001", constants.MIN_DIFFICULTY_LEVEL),
            _lemma("N01_002", constants.MAX_DIFFICULTY_LEVEL),
            _lemma("N01_003", constants.EXCLUDE_DIFFICULTY_LEVEL),
            _lemma("N01_004", constants.MAX_DIFFICULTY_LEVEL + 1),
        ]
    )
    session.flush()

    result = check_invalid_difficulty_levels(session)

    assert result["invalid_count"] == 1
    assert result["invalid_entries"][0]["guid"] == "N01_004"


def test_excluded_word_uses_level_after_supported_ceiling(session: Session) -> None:
    excluded = _lemma("N01_001", constants.EXCLUDE_DIFFICULTY_LEVEL)
    sentence = Sentence(guid="S_00001", minimum_level=21, rejected=False)
    session.add_all([excluded, sentence])
    session.flush()
    session.add(
        SentenceWordHint(
            sentence_id=sentence.id,
            lemma_id=excluded.id,
            position=0,
            slot_name="subject",
            english_text=excluded.lemma_text,
        )
    )
    session.flush()

    result = check_sentence_levels(session, fix=True)

    assert result["fixed_count"] == 1
    assert sentence.minimum_level == constants.MAX_DIFFICULTY_LEVEL + 1


def test_override_writer_uses_shared_level_bounds(session: Session) -> None:
    lemma = _lemma("N01_001", 1)
    session.add(lemma)
    session.flush()

    accepted = add_difficulty_override(
        session, lemma.id, "lt", constants.TOPIC_DIFFICULTY_LEVEL_MIN
    )
    assert accepted.difficulty_level == constants.TOPIC_DIFFICULTY_LEVEL_MIN

    with pytest.raises(ValueError, match="between 1 and 199"):
        add_difficulty_override(session, lemma.id, "zh", constants.MAX_DIFFICULTY_LEVEL + 1)
