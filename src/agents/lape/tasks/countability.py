"""
Countability Task - Classify nouns as countable, uncountable, or both.
"""

import logging
from typing import Optional, Tuple, TYPE_CHECKING

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.schema import Lemma

if TYPE_CHECKING:
    from agents.lape.agent import LapeAgent

logger = logging.getLogger(__name__)


def generate_countability(
    agent: "LapeAgent", lemma: Lemma, session=None
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate noun countability classification using LLM.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        session: Database session (optional)

    Returns:
        Tuple of (countability, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping countability")
        return None, None, 0.0

    # Load prompts
    try:
        context = util.prompt_loader.get_context("wordfreq", "countability")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "countability")
    except Exception as e:
        logger.error(f"Failed to load countability prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )

    # Define JSON schema for response
    schema = Schema(
        name="NounCountabilityClassification",
        description="Classify noun countability",
        properties={
            "countability": SchemaProperty(
                "string",
                "The countability classification",
                enum=["countable", "uncountable", "both"],
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation if notable"
            ),
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

        countability = result.get("countability", None)
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        logger.info(
            f"Generated countability for '{lemma.lemma_text}': {countability} "
            f"(confidence: {confidence:.2f})"
        )

        return countability, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate countability for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
