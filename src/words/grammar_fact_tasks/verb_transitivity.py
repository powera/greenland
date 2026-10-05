"""
Verb Transitivity Task - Classify verbs by transitivity.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall, Schema, SchemaProperty
from storage.models.schema import Lemma
from words.grammar_fact_tasks.common import (
    NO_FACT,
    FactResult,
    FactTask,
    interpret_field,
    load_prompt,
    run_live,
)

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)


def prepare_verb_transitivity(
    session: Optional[Session], lemma: Lemma, translation: Optional[str], language_code: str
) -> Union[LLMCall, FactResult]:
    """Build the transitivity request (English-based; translation unused)."""
    if lemma.pos_type != "verb":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping transitivity")
        return NO_FACT

    context, prompt_template = load_prompt("transitivity")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )
    schema = Schema(
        name="VerbTransitivityClassification",
        description="Classify verb transitivity",
        properties={
            "transitivity": SchemaProperty(
                "string",
                "The transitivity classification",
                enum=["transitive", "intransitive", "ditransitive", "ambitransitive"],
            ),
            "explanation": SchemaProperty("string", "Brief explanation if notable"),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


interpret_verb_transitivity = interpret_field("transitivity")

TASK = FactTask(prepare_verb_transitivity, interpret_verb_transitivity)


def generate_verb_transitivity(
    agent: "GrammarFactService", lemma: Lemma, session: Optional[Session] = None
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate verb transitivity classification using LLM.

    Returns:
        Tuple of (transitivity, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, None, "en", "transitivity")
