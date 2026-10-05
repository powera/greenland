"""
Animacy Task - Classify nouns as animate or inanimate.
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


def prepare_animacy(
    session: Optional[Session], lemma: Lemma, translation: Optional[str], language_code: str
) -> Union[LLMCall, FactResult]:
    """Build the animacy request (English-based; translation unused)."""
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping animacy")
        return NO_FACT

    context, prompt_template = load_prompt("animacy")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )
    schema = Schema(
        name="NounAnimacyClassification",
        description="Classify noun animacy",
        properties={
            "animacy": SchemaProperty(
                "string",
                "The animacy classification",
                enum=["animate", "inanimate"],
            ),
            "explanation": SchemaProperty("string", "Brief explanation if notable"),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


interpret_animacy = interpret_field("animacy")

TASK = FactTask(prepare_animacy, interpret_animacy)


def generate_animacy(
    agent: "GrammarFactService", lemma: Lemma, session: Optional[Session] = None
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate noun animacy classification using LLM.

    Returns:
        Tuple of (animacy, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, None, "en", "animacy")
