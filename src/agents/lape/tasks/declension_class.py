"""
Declension Class Task - Determine declension class for nouns.
"""

import logging
from typing import Optional, Tuple, TYPE_CHECKING

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.schema import Lemma

if TYPE_CHECKING:
    from agents.lape.agent import LapeAgent

logger = logging.getLogger(__name__)


def generate_declension_class(
    agent: "LapeAgent", lemma: Lemma, target_translation: str, language_code: str, session=None
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate noun declension class using LLM.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        target_translation: The translation in the target language
        language_code: Target language code (currently only 'lt' for Lithuanian)
        session: Database session (optional)

    Returns:
        Tuple of (declension_class, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping declension class")
        return None, None, 0.0

    if language_code != "lt":
        logger.error(f"Declension class only supported for Lithuanian, got '{language_code}'")
        return None, None, 0.0

    # Load prompts
    try:
        context = util.prompt_loader.get_context("wordfreq", "declension_class")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "declension_class")
    except Exception as e:
        logger.error(f"Failed to load declension_class prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )

    # Define JSON schema for response
    schema = Schema(
        name="LithuanianDeclensionClassification",
        description="Classify Lithuanian noun declension class",
        properties={
            "declension_class": SchemaProperty(
                "string",
                "The declension class (1-5)",
                enum=["1", "2", "3", "4", "5"],
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation with ending pattern"
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

        declension_class = result.get("declension_class", None)
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        logger.info(
            f"Generated declension class for '{lemma.lemma_text}' ({target_translation}): "
            f"class {declension_class} (confidence: {confidence:.2f})"
        )

        return declension_class, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate declension class for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
