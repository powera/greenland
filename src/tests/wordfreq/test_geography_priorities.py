"""Geography promotion follows curated senses and target-language context."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.models.schema import Base, Lemma, LemmaDifficultyOverride
from words.difficulty.country_override_manager import CountryOverrideManager
from words.difficulty.country_word_priorities import (
    get_country_level_for_language,
    validate_configuration,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _add(session: Session, text: str, subtype: str, pos: str = "noun", level: int = 231) -> Lemma:
    lemma = Lemma(
        guid=f"TEST_{pos}_{text}_{subtype}",
        lemma_text=text,
        definition_text=f"Test {text} {subtype}",
        pos_type=pos,
        pos_subtype=subtype,
        difficulty_level=level,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _levels(session: Session, language: str) -> dict[str, int]:
    return {
        change.guid: change.proposed_level
        for change in CountryOverrideManager(session)
        .preview_changes(language, include_unchanged=True)
        .changes
    }


def test_country_promotion_differs_between_lithuanian_and_chinese() -> None:
    assert get_country_level_for_language("Lithuania", "lt") == 15
    assert get_country_level_for_language("Lithuania", "zh") == 231
    assert get_country_level_for_language("China", "zh") == 15
    assert get_country_level_for_language("China", "lt") == 231
    assert get_country_level_for_language("Mongolia", "lt") == 1031
    assert get_country_level_for_language("Ukraine", "zh") == 231
    assert get_country_level_for_language("Mexico", "es-mx") == 15
    assert validate_configuration() == []


def test_person_and_language_follow_country_but_origin_does_not(session: Session) -> None:
    person = _add(session, "Lithuanian", "nationality")
    adjective = _add(session, "Lithuanian", "origin", "adjective")
    language = _add(session, "Lithuanian", "language_name")
    generic_origin = _add(session, "national", "origin", "adjective")
    for lemma in [person, language]:
        assert lemma.guid is not None
        assert _levels(session, "lt")[lemma.guid] == 15
        assert _levels(session, "zh")[lemma.guid] == (
            233 if lemma.pos_subtype == "language_name" else 232
        )
    assert generic_origin.guid not in _levels(session, "lt")
    assert adjective.guid not in _levels(session, "lt")
    assert adjective.guid not in _levels(session, "zh")


def test_existing_demonym_headwords_are_recognized(session: Session) -> None:
    pole = _add(session, "Pole", "nationality", level=230)
    chinese_person = _add(session, "Chinese person", "nationality", level=230)
    assert pole.guid is not None and chinese_person.guid is not None
    assert _levels(session, "lt")[pole.guid] == 15
    assert _levels(session, "zh")[chinese_person.guid] == 15


def test_shared_language_emits_one_change_using_earliest_association(session: Session) -> None:
    # Portuguese is associated with Portugal (main batch) and Brazil (tier 1).
    portuguese = _add(session, "Portuguese", "language_name", level=400)
    summary = CountryOverrideManager(session).preview_changes("es-419")
    assert [(change.guid, change.proposed_level) for change in summary.changes] == [
        (portuguese.guid, 15)
    ]
    assert summary.total_words_analyzed == 1


def test_extended_language_stays_extended_despite_country_promotion(session: Session) -> None:
    assamese = _add(session, "Assamese", "language_name", level=1033)
    mongolian = _add(session, "Mongolian", "language_name", level=1033)
    igbo = _add(session, "Igbo person", "nationality", level=1032)
    assert assamese.guid is not None and mongolian.guid is not None and igbo.guid is not None
    levels = _levels(session, "zh")
    assert levels[assamese.guid] == levels[mongolian.guid] == 1033
    assert levels[igbo.guid] == 1032


def test_new_main_country_senses_follow_promotion(session: Session) -> None:
    greek_person = _add(session, "Greek", "nationality", level=232)
    greek_language = _add(session, "Greek", "language_name", level=233)
    mexican = _add(session, "Mexican", "origin", "adjective", level=232)
    assert greek_person.guid and greek_language.guid and mexican.guid
    assert _levels(session, "lt")[greek_person.guid] == 232
    assert _levels(session, "lt")[greek_language.guid] == 233
    assert mexican.guid not in _levels(session, "es-419")


def test_country_sense_requires_its_disambiguation(session: Session) -> None:
    state = _add(session, "Georgia", "region", level=240)
    country = Lemma(
        guid="TEST_noun_Georgia_country",
        lemma_text="Georgia",
        definition_text="The country of Georgia.",
        pos_type="noun",
        pos_subtype="region",
        difficulty_level=1031,
        disambiguation="country",
    )
    session.add(country)
    session.flush()
    levels = _levels(session, "zh")
    assert state.guid not in levels
    assert country.guid is not None and levels[country.guid] == 1031


def test_apply_replaces_old_derived_levels_and_preserves_manual_override(session: Session) -> None:
    lithuania = _add(session, "Lithuania", "region", level=245)
    chinese = _add(session, "Chinese", "language_name")
    session.add_all(
        [
            LemmaDifficultyOverride(
                lemma_id=lithuania.id, language_code="lt", difficulty_level=10, notes=None
            ),
            LemmaDifficultyOverride(
                lemma_id=chinese.id,
                language_code="lt",
                difficulty_level=18,
                notes="Reviewed manually",
            ),
        ]
    )
    session.commit()
    manager = CountryOverrideManager(session)
    manager.apply_overrides("lt")
    assert (
        session.query(LemmaDifficultyOverride)
        .filter_by(lemma_id=lithuania.id)
        .one()
        .difficulty_level
        == 15
    )
    assert (
        session.query(LemmaDifficultyOverride).filter_by(lemma_id=chinese.id).one().difficulty_level
        == 18
    )
    assert manager.preview_changes("lt").words_with_changes == 0


def test_dry_run_does_not_persist_overrides(session: Session) -> None:
    _add(session, "Lithuania", "region", level=245)
    session.commit()
    CountryOverrideManager(session).apply_overrides("lt", dry_run=True)
    assert session.query(LemmaDifficultyOverride).count() == 0


def test_extended_country_override_is_not_mistaken_for_stale_state_data(session: Session) -> None:
    mongolia = _add(session, "Mongolia", "region", level=245)
    session.commit()
    manager = CountryOverrideManager(session)
    manager.apply_overrides("zh")
    override = session.query(LemmaDifficultyOverride).filter_by(lemma_id=mongolia.id).one()
    assert override.difficulty_level == 1031
    assert manager.preview_changes("zh").words_with_changes == 0
