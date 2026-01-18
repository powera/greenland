"""
Verb Transitivity Task - Classify verbs by transitivity.
"""

import logging
from typing import Optional, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.schema import Lemma

if TYPE_CHECKING:
    from agents.lape.agent import LapeAgent

logger = logging.getLogger(__name__)


def generate_verb_transitivity(
    agent: "LapeAgent", lemma: Lemma, session: Optional[Session] = None
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate verb transitivity classification using LLM.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        session: Database session (optional)

    Returns:
        Tuple of (transitivity, explanation, confidence)
    """
    if lemma.pos_type != "verb":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping transitivity")
        return None, None, 0.0

    # Load prompts
    try:
        context = util.prompt_loader.get_context("wordfreq", "verb_transitivity")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "verb_transitivity")
    except Exception as e:
        logger.error(f"Failed to load verb_transitivity prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )

    # Define JSON schema for response
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

    # Query LLM
    try:
        client = agent.get_llm_client()
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

        if response.structured_data:
            result = response.structured_data
        else:
            logger.error(f"No structured data received for '{lemma.lemma_text}'")
            return None, None, 0.0

        transitivity = result.get("transitivity", None)
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        logger.info(
            f"Generated transitivity for '{lemma.lemma_text}': {transitivity} "
            f"(confidence: {confidence:.2f})"
        )

        return transitivity, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate transitivity for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
