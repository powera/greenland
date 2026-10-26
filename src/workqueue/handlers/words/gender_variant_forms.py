"""Person nouns' male/female variant paradigms as a staged job (``vilkas --gender-variants``).

One item per (lemma, language, variant key).  English is built mechanically;
every other language's call is the generic forms prompt about the variant's
word, captured with a ``DeferringClient`` so it runs live or as OpenAI batches.
See words.gender_variant_forms.
"""

from __future__ import annotations

from typing import Any, Dict, Union

from sqlalchemy.orm import Session

from clients.deferring_client import DeferLLMCall, DeferringClient
from clients.types import LLMCall
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import (
    parse_forms_confidence,
    parse_forms_notes,
    parse_forms_response,
    query_forms,
)
from storage.models.schema import Lemma
from words.gender_variant_forms import (
    mechanical_variant_forms,
    noun_form_config,
    store_variant_forms,
    variant_base_row,
    variant_forms_complete,
)
from workqueue.llm_batch import Done, Job, Next, Ready, Stage, StageContext

GENDER_VARIANT_FORMS_JOB_NAME = "vilkas_gender_variants"
GENDER_VARIANT_FORMS_STAGE = "gender_variant_forms.generate"


def _prepare(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    language_code = state["language_code"]
    variant_key = state["variant_key"]
    form_config = noun_form_config(language_code)
    if form_config is None:
        return Done("rejected", f"No {language_code} noun form task")
    base = variant_base_row(session, lemma.id, language_code, variant_key)
    if base is None:
        return Done("rejected", f"No {variant_key} base word in {language_code}")
    if variant_forms_complete(session, lemma.id, variant_key, form_config):
        return Done("skipped", "forms already present")
    mechanical = mechanical_variant_forms(session, lemma, language_code, base.variant_form_text)
    if mechanical:
        return Ready({"forms": mechanical, "mechanical": True})
    try:
        forms, success = query_forms(
            FORM_SPECS[(language_code, "noun")],
            DeferringClient(ctx.model),  # type: ignore[arg-type]
            lemma.id,
            lambda: session,
            word=base.variant_form_text,
        )
    except DeferLLMCall as deferred:
        return deferred.call
    if success and forms:
        return Ready({"forms": forms, "mechanical": True})
    return Done("rejected", "no forms")


def _apply(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    form_config = noun_form_config(state["language_code"])
    if form_config is None:
        return Done("rejected", f"No {state['language_code']} noun form task")
    forms = parse_forms_response(data)
    if not forms:
        return Done("rejected", "answer had no forms")
    mechanical = bool(data.get("mechanical"))
    confidence = None if mechanical else parse_forms_confidence(data)
    stored = store_variant_forms(
        session,
        lemma,
        state["variant_key"],
        forms,
        form_config,
        notes=None if mechanical else parse_forms_notes(data),
        confidence=confidence,
        model=ctx.model,
    )
    if stored is None:
        return Done("rejected", f"forms at confidence {confidence or 0.0:.2f}")
    if stored:
        return Done("written", f"{stored} form(s)")
    return Done("skipped", "every form already present")


GENDER_VARIANT_FORMS_JOB = Job(
    name=GENDER_VARIANT_FORMS_JOB_NAME,
    stages=(Stage(GENDER_VARIANT_FORMS_STAGE, _prepare, _apply),),
    item_key=lambda state: f"{state['lemma_id']}:{state['language_code']}:{state['variant_key']}",
)
