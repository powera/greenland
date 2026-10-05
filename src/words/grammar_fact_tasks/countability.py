"""
Countability task - classify English noun usage as countable, uncountable, or both.
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


def prepare_countability(
    session: Optional[Session], lemma: Lemma, translation: Optional[str], language_code: str
) -> Union[LLMCall, FactResult]:
    """Build the English countability request (translation unused)."""
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping countability")
        return NO_FACT

    context, prompt_template = load_prompt("countability")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        disambiguation=lemma.disambiguation or "N/A",
        pos_subtype=lemma.pos_subtype or "N/A",
        definition=lemma.definition_text or "N/A",
    )
    schema = Schema(
        name="NounCountabilityClassification",
        description="Classify English noun phrase countability for this sense",
        properties={
            "countability": SchemaProperty(
                "string",
                "English count, mass, or both usage; independent of individual instances and number_type",
                enum=["countable", "uncountable", "both"],
            ),
            "explanation": SchemaProperty("string", "Brief explanation if notable"),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


interpret_countability = interpret_field("countability")

TASK = FactTask(prepare_countability, interpret_countability)


def generate_countability(
    agent: "GrammarFactService", lemma: Lemma, session: Optional[Session] = None
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate English noun countability classification using LLM.

    Returns:
        Tuple of (countability, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, None, "en", "countability")
