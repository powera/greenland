"""Tests for GENDER_VARIANT_FORMS_JOB: the paradigms of person nouns' male/female words."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from clients.types import LLMCall
from storage.crud.gender_variant import GenderVariantAnswer, store_gender_variant_answer
from storage.models.schema import Base, Lemma
from storage.models.variant_form import VARIANT_KIND_GENDER, VariantForm
from storage.translation_helpers import set_translation
from words.gender_variant_forms import gender_variant_form_states
from workqueue.handlers.words.gender_variant_forms import GENDER_VARIANT_FORMS_JOB
from workqueue.llm_batch import Done, Ready, StageContext
from workqueue.registry import get_llm_job

CTX = StageContext(model="gpt-test", via="inline")
STAGE = GENDER_VARIANT_FORMS_JOB.stages[0]


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


@pytest.fixture()
def actor(session: Session) -> Lemma:
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
    store_gender_variant_answer(
        session, lemma, "en", GenderVariantAnswer("actor", "actress"), "test"
    )
    store_gender_variant_answer(
        session,
        lemma,
        "es",
        GenderVariantAnswer("actor", "actriz", "masculine", "feminine"),
        "test",
    )
    return lemma


def _forms(session: Session, lemma: Lemma, language: str, key: str) -> dict[str, str]:
    return {
        row.grammatical_form: row.variant_form_text
        for row in session.query(VariantForm).filter_by(
            lemma_id=lemma.id,
            language_code=language,
            variant_kind=VARIANT_KIND_GENDER,
            variant_key=key,
        )
    }


def test_job_is_registered_for_batch_completion() -> None:
    assert get_llm_job("vilkas_gender_variants") is GENDER_VARIANT_FORMS_JOB


def test_states_list_each_incomplete_variant(session: Session, actor: Lemma) -> None:
    states = gender_variant_form_states(session, [actor], ["en", "es", "fr"])
    assert {(state["language_code"], state["variant_key"]) for state in states} == {
        ("en", "female"),
        ("en", "male"),
        ("es", "female"),
        ("es", "male"),
    }


def test_english_paradigm_is_mechanical(session: Session, actor: Lemma) -> None:
    state = {"lemma_id": actor.id, "language_code": "en", "variant_key": "female"}
    ready = STAGE.prepare(session, state, CTX)
    assert isinstance(ready, Ready)
    done = STAGE.apply(session, state, ready.data, CTX)
    assert isinstance(done, Done) and done.status == "written"
    assert _forms(session, actor, "en", "female")["noun/en_plural"] == "actresses"
    assert STAGE.prepare(session, state, CTX) == Done("skipped", "forms already present")


def test_other_languages_ask_about_the_variant_word(session: Session, actor: Lemma) -> None:
    state = {"lemma_id": actor.id, "language_code": "es", "variant_key": "female"}
    call = STAGE.prepare(session, state, CTX)
    assert isinstance(call, LLMCall)
    assert "actriz" in call.prompt

    done = STAGE.apply(
        session,
        state,
        {"forms": {"singular": "actriz", "plural": "actrices"}, "confidence": 0.9},
        CTX,
    )
    assert isinstance(done, Done) and done.status == "written"
    rows = {
        row.grammatical_form: (row.variant_form_text, row.grammatical_gender)
        for row in session.query(VariantForm).filter_by(
            lemma_id=actor.id, language_code="es", variant_key="female"
        )
    }
    assert rows["noun/es_plural"] == ("actrices", "feminine")
    # The base word is left as it was.
    assert rows["noun/es_singular"] == ("actriz", "feminine")


def test_uncertain_paradigm_is_skipped_until_retried(session: Session, actor: Lemma) -> None:
    state = {"lemma_id": actor.id, "language_code": "es", "variant_key": "male"}
    done = STAGE.apply(session, state, {"forms": {"plural": "actores"}, "confidence": 0.2}, CTX)
    assert isinstance(done, Done) and done.status == "rejected"
    keys = {
        (state["language_code"], state["variant_key"])
        for state in gender_variant_form_states(session, [actor], ["es"])
    }
    assert ("es", "male") not in keys
    retried = gender_variant_form_states(session, [actor], ["es"], retry_uncertain=True)
    assert ("es", "male") in {(s["language_code"], s["variant_key"]) for s in retried}
