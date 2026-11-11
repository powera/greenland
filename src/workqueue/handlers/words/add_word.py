"""Staged-job form of :func:`words.add_word.add_word`, for OpenAI batches.

``dramblys --stage-words`` builds one item per word and submits it through
``workqueue.llm_batch``; the Barsukas batch poller (or ``python -m
agents.common.batch complete``) applies each stage as its batch completes.

The two LLM calls of ``add_word`` become the two stages, built from the same
pieces, so a batched word is added exactly as a live one is:

1. ``words.add.senses`` -- the senses call (``build_definitions_prompt``, no
   subtype), then ``plan_senses``: the POS-directed frequency lookup and the
   frequency-sized sense selection.
2. ``words.add.subtypes`` -- one subtype call per selected sense with a real
   choice, as a fan-out: each sense is classified on its own, with only its own
   part of speech's subtypes in view, as the live path does.  The joined apply
   then runs ``write_senses``: validation, review routing, one lemma per sense.

The existence guard runs again before writing: a word added by hand (or by
another run) while its batch was out is skipped, not duplicated.  Lemma GUIDs
are minted inside ``write_senses`` through ``run_lemma_write``, serialized
with every other lemma write in the process; see ``storage.utils.guid``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall
from words.add_word import (
    SensePlan,
    check_word_absent,
    keep_pos,
    plan_senses,
    subtype_call,
    subtype_sense_indexes,
    write_senses,
)
from words.definitions import build_definitions_prompt
from words.lemma_creation import UNSET_DIFFICULTY_LEVEL
from workqueue.llm_batch import Done, FanOut, Job, Next, Ready, Stage, StageContext

ADD_WORD_JOB_NAME = "words_add"
SENSES_STAGE = "words.add.senses"
SUBTYPES_STAGE = "words.add.subtypes"


def add_word_state(
    word: str,
    *,
    source: str,
    difficulty_level: int = UNSET_DIFFICULTY_LEVEL,
    pos_type: Optional[str] = None,
) -> Dict[str, Any]:
    """The item state for one word to add."""
    return {
        "word": word.strip(),
        "source": source,
        "difficulty_level": difficulty_level,
        "pos_type": pos_type,
    }


def _prepare_senses(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    status = check_word_absent(session, state["word"], state.get("pos_type"))
    if status is not None:
        return Done("skipped", status)
    context, prompt, schema = build_definitions_prompt(
        state["word"], pos_type=state.get("pos_type"), ask_subtype=False
    )
    return LLMCall(prompt=prompt, schema=schema, context=context)


def _apply_senses(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    definitions = data.get("definitions") if isinstance(data, dict) else None
    if not isinstance(definitions, list) or not definitions:
        return Done("skipped", "no_definitions")
    definitions_list = keep_pos(definitions, state.get("pos_type"))
    if not definitions_list:
        return Done("skipped", "no_definitions")
    plan = plan_senses(session, state["word"], definitions_list, state.get("pos_type"))
    if not plan.senses:
        return Done("skipped", f"no_definitions; dropped {len(plan.dropped)}")
    return Next({**state, "plan": plan.to_state()})


def _prepare_subtypes(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[FanOut, Done]:
    plan = SensePlan.from_state(state["plan"])
    indexes = subtype_sense_indexes(plan)
    # subtype_sense_indexes filled in the closed-class senses; apply re-reads
    # the plan from the state, so keep what it wrote.
    state["plan"] = plan.to_state()
    return FanOut({str(index): subtype_call(plan.word, plan.senses[index]) for index in indexes})


def _apply_subtypes(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Done:
    plan = SensePlan.from_state(state["plan"])
    for part, answer in data.items():
        sense = plan.senses[int(part)]
        subtype = answer.get("pos_subtype") if isinstance(answer, dict) else None
        if not isinstance(subtype, str) or not subtype:
            definition_text = str(sense.get("definition") or "")
            return Done("failed", f"subtype call failed for sense {definition_text[:60]!r}")
        sense["pos_subtype"] = subtype

    # Added by hand, or by another run, while the batch was out.
    status = check_word_absent(session, plan.word, state.get("pos_type"))
    if status is not None:
        return Done("skipped", status)

    result = write_senses(
        session,
        plan,
        source=state["source"],
        model=ctx.model,
        difficulty_level=int(state["difficulty_level"]),
    )
    detail = (
        f"{result.status}: {len(result.senses)} lemma(s), "
        f"{len(result.pending_senses)} pending; {result.error or ''}".strip()
    )
    if result.status == "created":
        return Done("written", detail)
    if result.status == "pending_review":
        return Done("written", detail)
    if result.status == "error":
        return Done("failed", detail)
    return Done("skipped", detail)


ADD_WORD_JOB = Job(
    name=ADD_WORD_JOB_NAME,
    stages=(
        Stage(SENSES_STAGE, _prepare_senses, _apply_senses),
        Stage(SUBTYPES_STAGE, _prepare_subtypes, _apply_subtypes),
    ),
    item_key=lambda state: f"{state['word'].lower()}:{state.get('pos_type') or ''}",
    entity_type="word",
    entity_id_key="lemma_id",
)
