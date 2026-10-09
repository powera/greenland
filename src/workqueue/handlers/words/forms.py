"""Capability handlers for word form tasks.

``FORMS_JOB`` is the staged-job form ``workqueue.llm_batch`` runs as OpenAI
batches (``vilkas --populate --batch``).  It runs the live generators with a
``DeferringClient``, so every language's mechanical-first generator is batched
without changes of its own.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

from clients.deferring_client import DeferLLMCall, DeferringClient
from clients.types import LLMCall
from langtools.form_registry import FORM_SPECS
from langtools.form_tasks import generate_forms
from langtools.llm_forms_base import (
    parse_forms_confidence,
    parse_forms_notes,
    parse_forms_response,
)
from storage.database import log_query
from storage.models.schema import Lemma
from storage.translation_helpers import get_translation
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    forms_already_complete,
    forms_uncertain,
    store_generated_forms,
)
from wordfreq.translation.generate_forms_tasks import FORM_GENERATION_TASKS, get_task_key
from words.form_generation import generate_forms_for_lemma
from workqueue.llm_batch import Done, Job, Next, Ready, Stage, StageContext
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_forms(
    session: Any,
    lemma_id: int,
    language_code: str = "lt",
    lang_code: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate forms for a lemma/language pair."""
    effective_language_code = lang_code or language_code
    lemma = get_lemma_or_raise(session, lemma_id)
    success, error_message = generate_forms_for_lemma(session, lemma, effective_language_code)
    session.commit()
    if success:
        return f"Generated {effective_language_code} {lemma.pos_type} forms"
    raise RuntimeError(error_message)


@workqueue_payload_handler()
def handle_words_forms(
    session: Any,
    lemma_id: Optional[int] = None,
    lemma_ids: Optional[list[int]] = None,
    language_code: str = "lt",
    lang_code: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for form generation.

    Accepts and ignores extra payload kwargs (``model``, ``batch``, etc.) added
    by the route so it is tolerant of payload changes.
    """
    if lemma_ids:
        results = [
            do_generate_forms(
                session=session,
                lemma_id=queued_lemma_id,
                language_code=language_code,
                lang_code=lang_code,
            )
            for queued_lemma_id in lemma_ids
        ]
        return f"Batch completed for {len(lemma_ids)} lemmas: " + "; ".join(results)
    if lemma_id is None:
        raise ValueError("lemma_id or lemma_ids is required")
    return do_generate_forms(
        session=session,
        lemma_id=lemma_id,
        language_code=language_code,
        lang_code=lang_code,
    )


# ---------------------------------------------------------------------------
# Staged-job form, for batching (see workqueue.llm_batch)
# ---------------------------------------------------------------------------

FORMS_JOB_NAME = "vilkas"
FORMS_STAGE = "forms.generate"


def forms_state(
    lemma_id: int, language_code: str, pos_type: str, retry_uncertain: bool = False
) -> Dict[str, Any]:
    """The item state the forms job works on: one lemma in one language.

    A lemma whose forms a model was uncertain of is skipped unless
    ``retry_uncertain``.
    """
    return {
        "lemma_id": lemma_id,
        "language_code": language_code,
        "pos_type": pos_type,
        "retry_uncertain": retry_uncertain,
    }


def _form_config(language_code: str, pos_type: str) -> FormGenerationConfig:
    return FORM_GENERATION_TASKS[get_task_key(language_code, pos_type)].config


def _prepare_forms(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    language_code = state["language_code"]
    if lemma.pos_type != state["pos_type"]:
        return Done("rejected", f"Lemma is a {lemma.pos_type}, not a {state['pos_type']}")
    try:
        form_config = _form_config(language_code, lemma.pos_type)
    except KeyError:
        return Done("rejected", f"No {language_code} {lemma.pos_type} form task")
    if forms_already_complete(session, lemma.id, form_config):
        return Done("skipped", "forms already present")
    if not state.get("retry_uncertain") and forms_uncertain(session, lemma.id, form_config):
        return Done("skipped", "a model was uncertain of these forms")
    # The same generator the live path runs: a mechanical paradigm answers
    # here, and the LLM fallback surfaces as the call to batch.
    try:
        forms, success = generate_forms(
            language_code,
            lemma.pos_type,
            DeferringClient(ctx.model),
            lemma.id,
            lambda: session,
        )
    except DeferLLMCall as deferred:
        return deferred.call
    if success and forms:
        return Ready({"forms": forms, "mechanical": True})
    return Done("rejected", "no forms (missing translation?)")


def _apply_forms(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    language_code = state["language_code"]
    form_config = _form_config(language_code, lemma.pos_type)
    forms = parse_forms_response(data)
    if not data.get("mechanical"):
        # The live path logs every model answer; a batched one is logged here.
        spec = FORM_SPECS[(language_code, lemma.pos_type)]
        word = (
            lemma.lemma_text
            if spec.is_source_language
            else get_translation(session, lemma, language_code) or lemma.lemma_text
        )
        log_query(
            session,
            word=word,
            query_type=spec.query_type,
            prompt=f"[OpenAI batch, {ctx.via}]",
            response=json.dumps(data),
            model=ctx.model,
        )
    if not forms:
        return Done("rejected", "answer had no forms")
    # A mechanical paradigm has no confidence and is stored as it is.
    confidence = None if data.get("mechanical") else parse_forms_confidence(data)
    result = store_generated_forms(
        session,
        lemma.id,
        forms,
        form_config,
        notes=None if data.get("mechanical") else parse_forms_notes(data),
        confidence=confidence,
        model=ctx.model,
    )
    if result is None:
        return Done("rejected", f"forms at confidence {confidence or 0.0:.2f}")
    stored, facts_added = result
    if stored or facts_added:
        return Done("written", f"{stored} form(s), {facts_added} fact(s)")
    return Done("skipped", "every form already present")


FORMS_JOB = Job(
    name=FORMS_JOB_NAME,
    stages=(Stage(FORMS_STAGE, _prepare_forms, _apply_forms),),
    item_key=lambda state: f"{state['lemma_id']}:{state['language_code']}",
    # Mechanical paradigms record what they infer (lt gender, query logs) as
    # they run, so a dry run must not prepare.
    prepare_writes=True,
)
