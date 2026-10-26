"""The gender-variant check for person nouns that are already translated, as a staged job.

New translations answer the gender question inside voras's word prompt.  This
job asks it on its own for the languages a person noun already has: given the
ordinary word in each language, are there separate male and female words?  It
runs live or as OpenAI batches (``scripts/backfill_gender_variants.py``), one
item per lemma and group of at most 10 languages, and stores through
storage.crud.gender_variant, the writer voras uses.

A storage dialect whose word is its parent's (es-419 "actor" = es "actor")
copies the parent's answer without a model call: in the same item, right after
the parent's answer is stored, or at once if the parent was checked before.  A
dialect with a word of its own (es-419 "maestro") is asked like any language.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple, Union

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import LLMCall, Schema, SchemaProperty
from langtools.dialect_overrides import get_parent_language
from storage.crud.gender_variant import (
    asks_gender_variants,
    gender_answer_from_fields,
    gender_schema_properties,
    languages_per_request,
    get_gender_variant_status,
    needs_gender_variant_check,
    store_gender_variant_answer,
)
from storage.models.schema import Lemma
from storage.models.variant_form import (
    GENDER_VARIANT_FEMALE,
    GENDER_VARIANT_MALE,
    GENDER_VARIANT_STATUS_NONE,
)
from storage.translation_helpers import LANGUAGE_NAMES, get_translation, split_llm_language_batches
from words.gender_variant_forms import variant_base_row
from workqueue.llm_batch import Done, Job, Next, Ready, Stage, StageContext

GENDER_VARIANTS_JOB_NAME = "gender_variants"
GENDER_VARIANTS_STAGE = "gender_variants.check"


def _field(language_code: str) -> str:
    """The response key for one language ("es-419" -> "es_419")."""
    return language_code.replace("-", "_")


def ordinary_word(session: Session, lemma: Lemma, language_code: str) -> str:
    """The lemma's unspecified word in a language: English is the lemma itself."""
    if language_code == "en":
        return lemma.lemma_text
    return (get_translation(session, lemma, language_code) or "").strip()


def copied_answer(session: Session, lemma: Lemma, language_code: str) -> Dict[str, Any] | None:
    """A storage dialect's answer copied from its parent, or None.

    Only when the dialect's ordinary word is the parent's and the parent has
    been checked: the same word has the same male and female forms.
    """
    parent = get_parent_language(language_code)
    if parent == language_code:
        return None
    word = ordinary_word(session, lemma, language_code)
    if not word or word != ordinary_word(session, lemma, parent):
        return None
    status = get_gender_variant_status(session, lemma.id, parent)
    if status is None:
        return None
    if status == GENDER_VARIANT_STATUS_NONE:
        return {"male": "", "female": "", "confidence": 1.0}
    male = variant_base_row(session, lemma.id, parent, GENDER_VARIANT_MALE)
    female = variant_base_row(session, lemma.id, parent, GENDER_VARIANT_FEMALE)
    if male is None or female is None:
        return None
    return {
        "male": male.variant_form_text,
        "female": female.variant_form_text,
        "male_grammatical_gender": male.grammatical_gender or "",
        "female_grammatical_gender": female.grammatical_gender or "",
        "confidence": 1.0,
    }


def _shares_parent_word(session: Session, lemma: Lemma, language_code: str) -> bool:
    parent = get_parent_language(language_code)
    return parent != language_code and ordinary_word(session, lemma, language_code) == (
        ordinary_word(session, lemma, parent)
    )


def languages_to_check(
    session: Session, lemma: Lemma, languages: Sequence[str], replace: bool = False
) -> Tuple[List[str], List[str]]:
    """The languages to ask the model about, and the dialects that copy their parent.

    A language is due when unchecked (or always, with *replace*) and
    translated: one with no ordinary word has nothing to compare against, so
    it waits for its translation, which then asks the question itself.  A due
    dialect with its parent's word, whose parent is due here too, copies the
    parent's answer once it is stored instead of being asked.
    """
    if not asks_gender_variants(lemma):
        return [], []
    pending = [
        language_code
        for language_code in languages
        if (replace or needs_gender_variant_check(session, lemma, language_code))
        and ordinary_word(session, lemma, language_code)
    ]
    followers = [
        code
        for code in pending
        if get_parent_language(code) in pending and _shares_parent_word(session, lemma, code)
    ]
    return [code for code in pending if code not in followers], followers


def gender_variant_states(
    session: Session, lemmas: Sequence[Lemma], languages: Sequence[str], replace: bool = False
) -> Tuple[List[Dict[str, Any]], int]:
    """Item states for every person noun's languages to check.

    Each item asks at most ``languages_per_request`` languages; a dialect that
    copies its parent rides in its parent's item without adding to the request.

    Returns:
        ``(states, lemmas with nothing to ask)``.
    """
    states: List[Dict[str, Any]] = []
    complete = 0
    for lemma in lemmas:
        asked, followers = languages_to_check(session, lemma, languages, replace)
        if not asked:
            complete += 1
            continue
        for group in split_llm_language_batches(asked, languages_per_request(lemma)):
            riders = [code for code in followers if get_parent_language(code) in group]
            states.append(
                {"lemma_id": lemma.id, "languages": list(group) + riders, "replace": replace}
            )
    return states, complete


def build_gender_variant_call(session: Session, lemma: Lemma, languages: Sequence[str]) -> LLMCall:
    """The request asking about *languages* (at most 10) for one person noun."""
    language_words = "\n".join(
        f"- {LANGUAGE_NAMES.get(code, code)} ({_field(code)}): {ordinary_word(session, lemma, code)}"
        for code in languages
    )
    properties = {
        _field(code): SchemaProperty(
            "object",
            LANGUAGE_NAMES.get(code, code),
            properties={**gender_schema_properties(), "confidence": SchemaProperty("number")},
        )
        for code in languages
    }
    prompt = util.prompt_loader.get_prompt("translation", "gender_variants").format(
        english_word=lemma.lemma_text,
        definition=lemma.definition_text,
        pos_subtype=lemma.pos_subtype,
        language_words=language_words,
    )
    return LLMCall(
        prompt=prompt,
        schema=Schema(
            name="GenderVariants",
            description="Male and female words for a person noun, per language",
            properties=properties,
        ),
        context=util.prompt_loader.get_context("translation", "gender_variants"),
    )


def _prepare(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    if not asks_gender_variants(lemma):
        return Done("rejected", f"{lemma.guid} takes no gender variants")
    asked, followers = languages_to_check(
        session, lemma, state["languages"], bool(state.get("replace"))
    )
    if not asked:
        return Done("skipped", "every language already checked")
    state["asked"] = asked
    state["followers"] = followers
    copies: Dict[str, Dict[str, Any]] = {}
    for code in asked:
        copied = copied_answer(session, lemma, code)
        if copied is not None:
            copies[_field(code)] = copied
    state["copies"] = copies
    remaining = [code for code in asked if _field(code) not in copies]
    if not remaining:
        return Ready(dict(copies))
    return build_gender_variant_call(session, lemma, remaining)


def _confidence(fields: Dict[str, Any]) -> float:
    value = fields.get("confidence")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _apply(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    # Copied dialect answers ride along with the model's answer for the rest.
    data = {**state.get("copies", {}), **data}
    written: List[str] = []
    unanswered: List[str] = []
    not_stored: List[str] = []
    for language_code in state["asked"]:
        fields = data.get(_field(language_code))
        if not isinstance(fields, dict):
            unanswered.append(language_code)
            continue
        answer = gender_answer_from_fields(fields, ordinary_word(session, lemma, language_code))
        if answer is None:
            unanswered.append(language_code)
            continue
        status = store_gender_variant_answer(
            session,
            lemma,
            language_code,
            answer,
            f"gender-variants/{ctx.via}/{ctx.model}",
            bool(state.get("replace")),
            confidence=_confidence(fields),
            model=ctx.model,
        )
        if status is None:
            not_stored.append(language_code)
        else:
            written.append(f"{language_code}={status}")
    # Dialects with their parent's word copy the answer just stored for it.
    for language_code in state.get("followers", []):
        copied = copied_answer(session, lemma, language_code)
        answer = (
            gender_answer_from_fields(copied, ordinary_word(session, lemma, language_code))
            if copied is not None
            else None
        )
        status = (
            store_gender_variant_answer(
                session,
                lemma,
                language_code,
                answer,
                f"gender-variants/copied/{ctx.model}",
                bool(state.get("replace")),
            )
            if answer is not None
            else None
        )
        if status is None:
            not_stored.append(language_code)
        else:
            written.append(f"{language_code}={status} (copied)")
    detail = ", ".join(written)
    if not_stored:
        detail += f"; not stored (uncertain or one-sided): {', '.join(not_stored)}"
    if unanswered:
        detail += f"; no answer: {', '.join(unanswered)}"
    if written:
        return Done("written", detail)
    return Done("rejected", detail.lstrip("; "))


GENDER_VARIANTS_JOB = Job(
    name=GENDER_VARIANTS_JOB_NAME,
    stages=(Stage(GENDER_VARIANTS_STAGE, _prepare, _apply),),
    item_key=lambda state: f"{state['lemma_id']}:{'+'.join(state['languages'])}",
)
