"""Tests for GENDER_VARIANTS_JOB, the gender check for already-translated person nouns."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from clients.types import LLMCall
from storage.crud.gender_variant import GenderVariantAnswer, get_gender_variant_status
from storage.crud.gender_variant import store_gender_variant_answer
from storage.models.schema import Base, Lemma
from storage.translation_helpers import set_translation
from workqueue.handlers.words.gender_variants import (
    GENDER_VARIANTS_JOB,
    gender_variant_states,
)
from workqueue.llm_batch import Done, Ready, StageContext
from workqueue.registry import get_llm_job

CTX = StageContext(model="gpt-test", via="inline")


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


def _actor(session: Session) -> Lemma:
    lemma = Lemma(
        guid="N36_047",
        lemma_text="actor",
        definition_text="A person who acts in plays or films.",
        pos_type="noun",
        pos_subtype="occupation",
    )
    session.add(lemma)
    session.flush()
    set_translation(session, lemma, "es", "actor")
    set_translation(session, lemma, "zh", "演员")
    return lemma


def test_job_is_registered_for_batch_completion() -> None:
    assert get_llm_job("gender_variants") is GENDER_VARIANTS_JOB


def test_states_cover_unchecked_translated_languages_only(session: Session) -> None:
    actor = _actor(session)
    store_gender_variant_answer(session, actor, "zh", GenderVariantAnswer(), "test")
    dog = Lemma(guid="N02_001", lemma_text="dog", definition_text="A dog.", pos_type="noun")
    dog.pos_subtype = "animal"
    session.add(dog)
    session.flush()

    states, complete = gender_variant_states(session, [actor, dog], ["en", "es", "zh", "fr"])
    # zh is checked and fr untranslated; English is the lemma itself.
    assert states == [{"lemma_id": actor.id, "languages": ["en", "es"], "replace": False}]
    assert complete == 1


def test_prepare_and_apply_store_each_language(session: Session) -> None:
    actor = _actor(session)
    state = {"lemma_id": actor.id, "languages": ["en", "es"], "replace": False}
    stage = GENDER_VARIANTS_JOB.stages[0]
    call = stage.prepare(session, state, CTX)
    assert isinstance(call, LLMCall)
    assert "- Spanish (es): actor" in call.prompt
    assert set(call.schema.properties) == {"en", "es"}
    es_fields = call.schema.properties["es"].properties
    assert es_fields is not None and es_fields["gender_pattern"].enum is not None

    done = stage.apply(
        session,
        state,
        {
            "en": {"male": "actor", "female": "actress", "confidence": 0.9},
            "es": {
                "male": "actor",
                "female": "actriz",
                "male_grammatical_gender": "masculine",
                "female_grammatical_gender": "feminine",
                "confidence": 0.95,
            },
        },
        CTX,
    )
    assert isinstance(done, Done) and done.status == "written"
    assert get_gender_variant_status(session, actor.id, "en") == "pair"
    assert get_gender_variant_status(session, actor.id, "es") == "pair"
    assert stage.prepare(session, state, CTX) == Done("skipped", "every language already checked")


def test_apply_reports_missing_and_uncertain_languages(session: Session) -> None:
    actor = _actor(session)
    state = {"lemma_id": actor.id, "languages": ["en", "es"], "replace": False}
    stage = GENDER_VARIANTS_JOB.stages[0]
    stage.prepare(session, state, CTX)
    done = stage.apply(session, state, {"es": {"male": "", "female": "", "confidence": 0.2}}, CTX)
    assert isinstance(done, Done) and done.status == "rejected"
    assert "es" in done.detail and "no answer: en" in done.detail
    assert get_gender_variant_status(session, actor.id, "es") is None


def test_dialect_with_its_parents_word_copies_it_in_the_same_item(session: Session) -> None:
    actor = _actor(session)
    set_translation(session, actor, "es-419", "actor")
    states, _complete = gender_variant_states(session, [actor], ["es", "es-419"])
    assert [state["languages"] for state in states] == [["es", "es-419"]]

    state = states[0]
    stage = GENDER_VARIANTS_JOB.stages[0]
    call = stage.prepare(session, state, CTX)
    assert isinstance(call, LLMCall)
    assert set(call.schema.properties) == {"es"}
    done = stage.apply(
        session,
        state,
        {
            "es": {
                "gender_pattern": "separate_words",
                "male": "actor",
                "female": "actriz",
                "confidence": 0.9,
            }
        },
        CTX,
    )
    assert isinstance(done, Done) and done.status == "written"
    assert "es-419=pair (copied)" in done.detail
    assert get_gender_variant_status(session, actor.id, "es-419") == "pair"


def test_dialect_copies_a_parent_checked_earlier_without_a_call(session: Session) -> None:
    actor = _actor(session)
    set_translation(session, actor, "es-419", "actor")
    store_gender_variant_answer(
        session,
        actor,
        "es",
        GenderVariantAnswer("actor", "actriz", "masculine", "feminine"),
        "test",
    )
    state = {"lemma_id": actor.id, "languages": ["es-419"], "replace": False}
    stage = GENDER_VARIANTS_JOB.stages[0]
    ready = stage.prepare(session, state, CTX)
    assert isinstance(ready, Ready)
    done = stage.apply(session, state, ready.data, CTX)
    assert isinstance(done, Done) and done.status == "written"
    assert get_gender_variant_status(session, actor.id, "es-419") == "pair"


def test_dialect_with_its_own_word_is_asked(session: Session) -> None:
    actor = _actor(session)
    set_translation(session, actor, "es-419", "intérprete")
    states, _complete = gender_variant_states(session, [actor], ["es", "es-419"])
    assert [state["languages"] for state in states] == [["es", "es-419"]]
    call = GENDER_VARIANTS_JOB.stages[0].prepare(session, states[0], CTX)
    assert isinstance(call, LLMCall)
    assert set(call.schema.properties) == {"es", "es_419"}
    assert "intérprete" in call.prompt


def test_common_gender_answer_uses_the_ordinary_word(session: Session) -> None:
    artist = Lemma(
        guid="N36_031",
        lemma_text="artist",
        definition_text="A person who makes art.",
        pos_type="noun",
        pos_subtype="occupation",
    )
    session.add(artist)
    session.flush()
    set_translation(session, artist, "es", "artista")
    state = {"lemma_id": artist.id, "languages": ["es"], "replace": False}
    stage = GENDER_VARIANTS_JOB.stages[0]
    stage.prepare(session, state, CTX)
    done = stage.apply(
        session, state, {"es": {"gender_pattern": "common_gender", "confidence": 0.9}}, CTX
    )
    assert isinstance(done, Done) and done.status == "written"
    assert get_gender_variant_status(session, artist.id, "es") == "pair"
