"""Capability handlers for word grammar fact tasks.

Two entry points share the same prepare/interpret/save functions from
``words``: the workqueue task handler (one fact, live call), and
``GRAMMAR_FACT_JOB``, the staged-job form ``workqueue.llm_batch`` runs as
OpenAI batches (``lape --populate --batch``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall
from storage.crud.grammar_fact import get_grammar_fact_value
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.models.schema import Lemma
from storage.translation_helpers import get_translation
from words.grammar_fact_generation import (
    generate_grammar_fact_for_lemma,
    save_generated_fact,
    validate_grammar_fact_request,
)
from words.grammar_fact_tasks import FACT_TASKS
from words.grammar_fact_tasks.common import FactResult
from workqueue.llm_batch import Done, Job, Next, Ready, Stage, StageContext
from workqueue.tools import get_lemma_or_raise, workqueue_payload_handler


def do_generate_grammar_fact(
    session: Any,
    lemma_id: int,
    fact_type: str,
    language_code: str = "en",
    lang_code: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate one grammar fact for one lemma."""
    effective_language_code = lang_code or language_code
    lemma = get_lemma_or_raise(session, lemma_id)
    result = generate_grammar_fact_for_lemma(session, lemma, fact_type, effective_language_code)

    session.commit()

    if result.get("skipped"):
        return f"Skipped: {fact_type} already exists ({result.get('existing_value')})"
    if result.get("error"):
        raise RuntimeError(result["error"])

    return f"Generated {fact_type}: {result['fact_value']} (confidence: {result['confidence']:.2f})"


@workqueue_payload_handler()
def handle_words_grammar_facts(
    session: Any,
    lemma_id: int,
    fact_type: str,
    language_code: str = "en",
    lang_code: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for grammar fact generation.

    Accepts and ignores extra payload kwargs (``model``, etc.) added by the
    route so it is tolerant of payload changes.
    """
    return do_generate_grammar_fact(
        session=session,
        lemma_id=lemma_id,
        fact_type=fact_type,
        language_code=language_code,
        lang_code=lang_code,
    )


# ---------------------------------------------------------------------------
# Staged-job form, for batching (see workqueue.llm_batch)
# ---------------------------------------------------------------------------

GRAMMAR_FACT_JOB_NAME = "lape"
GRAMMAR_FACT_STAGE = "grammar_facts.generate"
DEFAULT_MIN_CONFIDENCE = 0.7

# Marks a Ready answer that is already a FactResult (a rule or a copy), so
# apply stores it as it is.  Model output never has keys like this.
_PRECOMPUTED = "__precomputed_fact__"


def grammar_fact_state(
    lemma_id: int,
    language_code: str,
    fact_type: str,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    retry_uncertain: bool = False,
) -> Dict[str, Any]:
    """The item state the grammar-fact job works on.

    ``retry_uncertain`` asks again where a model was uncertain before
    (uncertain_llm_results); by default those items are skipped.
    """
    return {
        "lemma_id": lemma_id,
        "language_code": language_code,
        "fact_type": fact_type,
        "min_confidence": min_confidence,
        "retry_uncertain": retry_uncertain,
    }


def _prepare_grammar_fact(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    fact_type = state["fact_type"]
    language_code = state["language_code"]
    task = FACT_TASKS.get(fact_type)
    if task is None:
        return Done("failed", f"{fact_type} cannot run as a staged job")
    if get_grammar_fact_value(session, lemma.id, language_code, fact_type) is not None:
        return Done("skipped", "already present")
    if not state.get("retry_uncertain") and get_uncertain_llm_result(
        session, fact_type, language_code, lemma_id=lemma.id
    ):
        return Done("skipped", "model was uncertain before")
    is_valid, error, translation = validate_grammar_fact_request(
        lemma, fact_type, language_code, session
    )
    if not is_valid:
        return Done("rejected", error or "invalid")
    prepared = task.prepare(session, lemma, translation, language_code)
    if isinstance(prepared, FactResult):
        if not prepared.value:
            return Done("rejected", "does not apply to this lemma")
        return Ready({_PRECOMPUTED: list(prepared)})
    return prepared


def _apply_grammar_fact(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    fact_type = state["fact_type"]
    language_code = state["language_code"]
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    if _PRECOMPUTED in data:
        value, notes, confidence = data[_PRECOMPUTED]
        result = FactResult(value, notes, float(confidence))
    else:
        translation = get_translation(session, lemma, language_code)
        result = FACT_TASKS[fact_type].interpret(data, translation, language_code)
    outcome = save_generated_fact(
        session,
        lemma.id,
        language_code,
        fact_type,
        result,
        float(state.get("min_confidence", DEFAULT_MIN_CONFIDENCE)),
        ctx.model,
        via=ctx.via,
    )
    if outcome == "written":
        return Done("written", str(result.value))
    if outcome == "exists":
        return Done("skipped", "already present")
    return Done("rejected", f"{result.value!r} at confidence {result.confidence:.2f}")


GRAMMAR_FACT_JOB = Job(
    name=GRAMMAR_FACT_JOB_NAME,
    stages=(Stage(GRAMMAR_FACT_STAGE, _prepare_grammar_fact, _apply_grammar_fact),),
    item_key=lambda state: f"{state['lemma_id']}:{state['language_code']}:{state['fact_type']}",
)
