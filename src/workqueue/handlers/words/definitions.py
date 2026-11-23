"""Capability handler for native definitions: ežys's staged job.

``DEFINITIONS_JOB`` is one item per lemma and group of at most 10 languages,
run live (``agents.ezys populate``) or as OpenAI batches (``--batch``) by
``workqueue.llm_batch``; the pieces live in ``words.definition_populate``.
"""

from typing import Any, Dict, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall
from storage.models.schema import Lemma
from words.definition_populate import (
    DEFAULT_MIN_CONFIDENCE,
    build_definition_call,
    describe_outcome,
    missing_definition_languages,
    store_definitions,
)
from workqueue.llm_batch import Done, Job, Stage, StageContext

DEFINITIONS_JOB_NAME = "ezys"
DEFINITIONS_STAGE = "definitions.populate"


def prepare(session: Session, state: Dict[str, Any], ctx: StageContext) -> Union[LLMCall, Done]:
    """Build the request for the state's languages that still need a definition.

    Re-checked at preparation, so a language defined by hand (or by another
    run) since the run was planned is not paid for.
    """
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    missing = missing_definition_languages(
        session,
        lemma,
        state["languages"],
        retry_uncertain=bool(state.get("retry_uncertain")),
        replace_existing=bool(state.get("replace_existing")),
    )
    if not missing:
        return Done("skipped", "definitions already present, uncertain, or untranslated")
    state["asked"] = missing
    return build_definition_call(session, lemma, missing)


def apply(session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext) -> Done:
    """Store the answer for the languages that were asked."""
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    outcome = store_definitions(
        session,
        lemma,
        data,
        state["asked"],
        model=ctx.model,
        source=f"ezys-agent/{ctx.via}/{ctx.model}",
        min_confidence=float(state.get("min_confidence", DEFAULT_MIN_CONFIDENCE)),
        replace_existing=bool(state.get("replace_existing")),
    )
    detail = describe_outcome(outcome)
    if outcome.written:
        return Done("written", detail)
    if outcome.uncertain or outcome.blank:
        return Done("rejected", detail)
    return Done("skipped", detail)


def item_key(state: Dict[str, Any]) -> str:
    return f"{state['lemma_id']}:{'+'.join(state['languages'])}"


DEFINITIONS_JOB = Job(
    name=DEFINITIONS_JOB_NAME,
    stages=(Stage(DEFINITIONS_STAGE, prepare, apply),),
    item_key=item_key,
)
