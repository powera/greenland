"""Staged-job form of jonvabalis's pending-import review, for OpenAI batches.

``jonvabalis --batch`` builds one item per queued row and submits it through
``workqueue.llm_batch``; the Barsukas batch poller (or ``python -m
agents.common.batch complete``) applies each verdict when its batch completes.
Prepare and apply are the live agent's own prompt and settling code, so a
batched row is judged and settled exactly as a sequential one is.

Prepare records the ids of the lemmas its prompt showed, and apply hands them
to :meth:`agents.jonvabalis.JonvabalisAgent.approve_distinct`, which leaves a
row queued when its head word gained a lemma after the prompt was built.
"""

from __future__ import annotations

from typing import Any, Dict, Union

from sqlalchemy.orm import Session

from agents.jonvabalis import (
    RESPONSE_SCHEMA,
    JonvabalisAgent,
    build_context,
    build_prompt,
    prompt_senses,
    shown_lemma_ids,
)
from clients.lib import schema_from_dict
from clients.types import LLMCall
from storage.backend.config import DataSourceConfig
from storage.models.imports import PendingImport
from workqueue.llm_batch import Done, Job, Next, Ready, Stage, StageContext

JONVABALIS_JOB_NAME = "jonvabalis"
REVIEW_STAGE = "pending_imports.review"


def review_state(pending: PendingImport) -> Dict[str, Any]:
    """The item state for one queued row.

    The proposed word is kept so a row rewritten between submission and
    completion (by hand, in Barsukas) is not settled by a verdict on its old text.
    """
    return {"pending_id": int(pending.id), "english_word": pending.english_word}


def _current_row(session: Session, state: Dict[str, Any]) -> Union[PendingImport, Done]:
    pending = session.get(PendingImport, state["pending_id"])
    if pending is None:
        return Done("skipped", "pending row is gone")
    if pending.english_word != state["english_word"]:
        return Done("skipped", f"row now proposes {pending.english_word!r}")
    return pending


def _prepare_review(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    pending = _current_row(session, state)
    if isinstance(pending, Done):
        return pending
    existing_senses, proposed_senses = prompt_senses(session, pending)
    state["shown_lemma_ids"] = shown_lemma_ids(existing_senses, proposed_senses)
    return LLMCall(
        prompt=build_prompt(pending, existing_senses, proposed_senses),
        schema=schema_from_dict(RESPONSE_SCHEMA),
        context=build_context(pending.pos_type),
    )


def _apply_review(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    pending = _current_row(session, state)
    if isinstance(pending, Done):
        return pending
    agent = JonvabalisAgent(DataSourceConfig(model=ctx.model))
    outcome = agent.apply_decision(session, pending, data, state.get("shown_lemma_ids", []))
    action = outcome.get("action")
    detail = f"{data.get('verdict')}: {data.get('reasoning') or ''}".strip()
    if not outcome.get("success"):
        return Done("failed", str(outcome.get("error") or action))
    if action == "left_in_queue":
        return Done("skipped", f"left in queue ({outcome.get('reason')}); {detail}")
    if action == "approved":
        return Done("written", f"approved -> lemma {outcome.get('lemma_id')}; {detail}")
    return Done("written", f"{action}; {detail}")


JONVABALIS_JOB = Job(
    name=JONVABALIS_JOB_NAME,
    stages=(Stage(REVIEW_STAGE, _prepare_review, _apply_review),),
    item_key=lambda state: str(state["pending_id"]),
    entity_type="pending_import",
    entity_id_key="pending_id",
)
