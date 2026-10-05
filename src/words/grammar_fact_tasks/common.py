"""Shared pieces of the grammar-fact tasks.

Each task module is split in two so the same request can be sent live or
through the OpenAI Batch API:

* ``prepare_<fact>(session, lemma, translation, language_code)`` builds the
  ``LLMCall`` -- prompt, context and schema -- or returns a ``FactResult``
  directly when no model is needed (a rule, a copy) or the lemma does not
  qualify (``NO_FACT``).  It never writes.
* ``interpret_<fact>(data, translation, language_code)`` turns the model's
  structured answer into a ``FactResult``.

``generate_<fact>(agent, ...)`` keeps its old signature and runs the two around
a live call through :func:`run_live`.  The batch path is
``workqueue.handlers.words.grammar_facts``.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, NamedTuple, Optional, Tuple, Union

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.lib import LLMCallsDisabledError
from clients.types import LLMCall
from storage.models.schema import Lemma

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)


class FactResult(NamedTuple):
    """A generated fact: its value (None for no fact), notes and confidence."""

    value: Optional[str]
    notes: Optional[str]
    confidence: float


NO_FACT = FactResult(None, None, 0.0)

PrepareFn = Callable[[Optional[Session], Lemma, Optional[str], str], Union[LLMCall, FactResult]]
InterpretFn = Callable[[Dict[str, Any], Optional[str], str], FactResult]


class FactTask(NamedTuple):
    prepare: PrepareFn
    interpret: InterpretFn


def load_prompt(prompt_name: str) -> Tuple[str, str]:
    """Return ``(context, prompt_template)`` for prompts/grammar/<prompt_name>."""
    context = util.prompt_loader.get_context("grammar", prompt_name)
    prompt_template = util.prompt_loader.get_prompt("grammar", prompt_name)
    return context, prompt_template


def interpret_field(value_field: str) -> InterpretFn:
    """The common answer shape: ``{value_field, explanation, confidence}``."""

    def interpret(
        data: Dict[str, Any], translation: Optional[str], language_code: str
    ) -> FactResult:
        return FactResult(
            data.get(value_field),
            data.get("explanation", ""),
            float(data.get("confidence", 0.5)),
        )

    return interpret


def run_live(
    agent: "GrammarFactService",
    task: FactTask,
    session: Optional[Session],
    lemma: Lemma,
    translation: Optional[str],
    language_code: str,
    label: str,
) -> Tuple[Optional[str], Optional[str], float]:
    """prepare -> live call -> interpret, as the ``generate_<fact>`` functions do.

    A failed call or an empty answer is logged and reported as no fact, as
    before the split; a disabled-LLM error is raised so a run under the kill
    switch stops instead of quietly reporting every lemma as failed.
    """
    try:
        prepared = task.prepare(session, lemma, translation, language_code)
    except Exception as e:
        logger.error(f"Failed to prepare {label} for '{lemma.lemma_text}': {e}")
        return NO_FACT
    if isinstance(prepared, FactResult):
        return prepared

    try:
        response = agent.get_llm_client().generate_chat(**prepared.chat_kwargs())
        if not response.structured_data:
            logger.error(f"No structured data received for '{lemma.lemma_text}'")
            return NO_FACT
        result = task.interpret(response.structured_data, translation, language_code)
    except LLMCallsDisabledError:
        raise
    except Exception as e:
        logger.error(f"Failed to generate {label} for '{lemma.lemma_text}': {e}")
        return NO_FACT

    logger.info(
        f"Generated {label} for '{lemma.lemma_text}'"
        f"{f' ({translation})' if translation else ''}: {result.value} "
        f"(confidence: {result.confidence:.2f})"
    )
    return result
