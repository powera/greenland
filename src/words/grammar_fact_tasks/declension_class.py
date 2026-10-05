"""
Declension Class Task - Determine declension class for nouns.
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


def prepare_declension_class(
    session: Optional[Session],
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
) -> Union[LLMCall, FactResult]:
    """Build the Lithuanian declension-class request."""
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping declension class")
        return NO_FACT

    if language_code != "lt":
        logger.error(f"Declension class only supported for Lithuanian, got '{language_code}'")
        return NO_FACT

    context, prompt_template = load_prompt("declension")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )
    schema = Schema(
        name="LithuanianDeclensionClassification",
        description="Classify Lithuanian noun declension class",
        properties={
            "declension_class": SchemaProperty(
                "string",
                "The declension class (1-5)",
                enum=["1", "2", "3", "4", "5"],
            ),
            "explanation": SchemaProperty("string", "Brief explanation with ending pattern"),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


interpret_declension_class = interpret_field("declension_class")

TASK = FactTask(prepare_declension_class, interpret_declension_class)


def generate_declension_class(
    agent: "GrammarFactService",
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate noun declension class using LLM (currently only 'lt').

    Returns:
        Tuple of (declension_class, explanation, confidence)
    """
    return run_live(
        agent, TASK, session, lemma, target_translation, language_code, "declension class"
    )
