"""
Verb Reflexivity Task - Classify verbs by reflexivity.
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
from words.grammar_fact_tasks.systems import REFLEXIVITY_SYSTEMS

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)


def prepare_verb_reflexivity(
    session: Optional[Session],
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
) -> Union[LLMCall, FactResult]:
    """Build the reflexivity request for *language_code*."""
    if lemma.pos_type != "verb":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping reflexivity")
        return NO_FACT

    if language_code not in REFLEXIVITY_SYSTEMS:
        logger.error(f"Language '{language_code}' does not have reflexivity configuration")
        return NO_FACT

    reflex_config = REFLEXIVITY_SYSTEMS[language_code]
    language_name = reflex_config["name"]

    context, prompt_template = load_prompt("reflexivity")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
        language_name=language_name,
        language_code=language_code,
    )
    schema = Schema(
        name="VerbReflexivityClassification",
        description=f"Classify verb reflexivity for {language_name}",
        properties={
            "reflexivity": SchemaProperty(
                "string",
                "The reflexivity classification",
                enum=list(reflex_config["values"]),
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation with reflexive form if applicable"
            ),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


interpret_verb_reflexivity = interpret_field("reflexivity")

TASK = FactTask(prepare_verb_reflexivity, interpret_verb_reflexivity)


def generate_verb_reflexivity(
    agent: "GrammarFactService",
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate verb reflexivity classification using LLM.

    Returns:
        Tuple of (reflexivity, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, target_translation, language_code, "reflexivity")
