"""Native definitions: what is asked, at what register, and what is stored."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import constants
import storage.models  # noqa: F401 -- register every model before create_all
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.models.curriculum_level import CurriculumLevel
from storage.models.schema import Base, Lemma, LemmaDifficultyOverride
from storage.models.uncertain_llm_result import TOPIC_DEFINITION
from storage.translation_helpers import get_definition, set_definition, set_translation
from words.definition_populate import (
    build_definition_call,
    definition_register,
    definition_source,
    missing_definition_languages,
    store_definitions,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture
def owl(session: Session) -> Lemma:
    lemma = Lemma(
        guid="N08_901",
        lemma_text="owl",
        definition_text="A bird of prey that hunts at night.",
        pos_type="noun",
        pos_subtype="animal",
        difficulty_level=7,
    )
    session.add(lemma)
    session.flush()
    for code, text in (("fr", "hibou"), ("lt", "pelėda"), ("de", "Eule")):
        set_translation(session, lemma, code, text)
    session.commit()
    session.refresh(lemma)
    return lemma


@pytest.mark.parametrize(
    "word_cefr, register",
    [
        (None, "B1"),
        ("", "B1"),
        ("A1", "B1"),
        ("A2.2", "B1"),
        ("B1", "B1"),
        ("B2", "B1"),
        ("B2.1", "B1"),
        ("C1", "B2"),
        ("C2", "C1"),
        ("nonsense", "B1"),
    ],
)
def test_register_is_a_step_below_the_word_never_below_b1(
    word_cefr: str | None, register: str
) -> None:
    assert definition_register(word_cefr) == register


def test_only_translated_undefined_non_english_languages_are_asked(
    session: Session, owl: Lemma
) -> None:
    set_definition(session, owl, "de", "Ein Vogel, der nachts jagt.")
    session.commit()
    # en is the lemma's own definition; zh has no translation; de is done.
    assert missing_definition_languages(session, owl, ["en", "fr", "zh", "de", "lt"]) == [
        "fr",
        "lt",
    ]
    assert missing_definition_languages(session, owl, ["de", "fr"], replace_existing=True) == [
        "de",
        "fr",
    ]


def test_excluded_languages_are_never_asked(session: Session, owl: Lemma) -> None:
    session.add(
        LemmaDifficultyOverride(
            lemma_id=owl.id,
            language_code="lt",
            difficulty_level=constants.EXCLUDE_DIFFICULTY_LEVEL,
        )
    )
    session.commit()
    assert missing_definition_languages(session, owl, ["fr", "lt"], retry_uncertain=True) == ["fr"]


def test_low_confidence_is_recorded_and_skipped_until_retried(session: Session, owl: Lemma) -> None:
    outcome = store_definitions(
        session,
        owl,
        {
            "fr": {"definition": "Oiseau qui chasse la nuit.", "confidence": 0.9},
            "lt": {"definition": "Paukštis.", "confidence": 0.3},
        },
        ["fr", "lt"],
        model="test-model",
        source="test",
    )
    session.commit()
    assert outcome.written == ["fr"] and outcome.uncertain == ["lt"]
    assert get_definition(session, owl, "fr") == "Oiseau qui chasse la nuit."
    assert get_definition(session, owl, "lt") is None
    assert missing_definition_languages(session, owl, ["fr", "lt"]) == []
    assert missing_definition_languages(session, owl, ["fr", "lt"], retry_uncertain=True) == ["lt"]

    # A hand-written definition answers the uncertain question.
    set_definition(session, owl, "lt", "Naktį medžiojantis plėšrus paukštis.")
    session.commit()
    assert get_uncertain_llm_result(session, TOPIC_DEFINITION, "lt", lemma_id=owl.id) is None


def test_existing_definitions_survive_unless_regenerating(session: Session, owl: Lemma) -> None:
    set_definition(session, owl, "fr", "Rapace nocturne.")
    answer = {"fr": {"definition": "Oiseau de nuit.", "confidence": 0.95}}

    kept = store_definitions(session, owl, answer, ["fr"], model="m", source="test")
    assert kept.skipped == ["fr"]
    assert get_definition(session, owl, "fr") == "Rapace nocturne."

    replaced = store_definitions(
        session, owl, answer, ["fr"], model="m", source="test", replace_existing=True
    )
    assert replaced.written == ["fr"]
    assert get_definition(session, owl, "fr") == "Oiseau de nuit."


def test_blank_answers_and_vanished_translations_write_nothing(
    session: Session, owl: Lemma
) -> None:
    outcome = store_definitions(
        session,
        owl,
        {
            "fr": {"definition": "  ", "confidence": 0.9},
            "zh": {"definition": "鸟", "confidence": 1},
        },
        ["fr", "zh"],
        model="m",
        source="test",
    )
    assert outcome.blank == ["fr"] and outcome.skipped == ["zh"] and not outcome.written


def test_set_definition_blank_clears(session: Session, owl: Lemma) -> None:
    set_definition(session, owl, "fr", "Oiseau de nuit.")
    set_definition(session, owl, "fr", "   ")
    assert get_definition(session, owl, "fr") is None


def test_call_carries_the_sense_register_and_one_key_per_language(
    session: Session, owl: Lemma
) -> None:
    session.add(CurriculumLevel(level=7, name="Animals", cefr="C1"))
    owl.disambiguation = "bird"
    session.commit()

    call = build_definition_call(session, owl, ["fr", "lt"])

    assert set(call.schema.properties) == {"fr", "lt"}
    assert "CEFR B2" in call.prompt
    assert "hibou" in call.prompt and "pelėda" in call.prompt
    assert "Eule" not in call.prompt  # only the asked languages' words
    assert call.context and "Do NOT translate the English definition" in call.context
    source = definition_source(owl, ["fr", "lt"])
    assert source["english_sense_note"] == "bird"
    assert source["words"] == {"fr": "hibou", "lt": "pelėda"}


def test_call_without_a_level_uses_the_floor(session: Session, owl: Lemma) -> None:
    owl.difficulty_level = None
    assert "CEFR B1" in build_definition_call(session, owl, ["fr"]).prompt


def test_call_needs_languages(session: Session, owl: Lemma) -> None:
    with pytest.raises(ValueError):
        build_definition_call(session, owl, [])
