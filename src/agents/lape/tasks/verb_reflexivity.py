"""
Verb Reflexivity Task - Classify verbs by reflexivity.
"""

import logging
from typing import List, Optional, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.schema import Lemma

if TYPE_CHECKING:
    from agents.lape.agent import LapeAgent

logger = logging.getLogger(__name__)


def generate_verb_reflexivity(
    agent: "LapeAgent",
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate verb reflexivity classification using LLM.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        target_translation: The translation in the target language
        language_code: Target language code
        session: Database session (optional)

    Returns:
        Tuple of (reflexivity, explanation, confidence)
    """
    if lemma.pos_type != "verb":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping reflexivity")
        return None, None, 0.0

    if language_code not in agent.REFLEXIVITY_SYSTEMS:
        logger.error(f"Language '{language_code}' does not have reflexivity configuration")
        return None, None, 0.0

    reflex_config = agent.REFLEXIVITY_SYSTEMS[language_code]
    language_name = reflex_config["name"]

    # Load prompts
    try:
        context = util.prompt_loader.get_context("wordfreq", "verb_reflexivity")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "verb_reflexivity")
    except Exception as e:
        logger.error(f"Failed to load verb_reflexivity prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
        language_name=language_name,
        language_code=language_code,
    )

    # Define JSON schema for response
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

    # Query LLM
    try:
        client = agent.get_llm_client()
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)

        if response.structured_data:
            result = response.structured_data
        else:
            logger.error(f"No structured data received for '{lemma.lemma_text}'")
            return None, None, 0.0

        reflexivity = result.get("reflexivity", None)
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        logger.info(
            f"Generated reflexivity for '{lemma.lemma_text}' ({target_translation}): "
            f"{reflexivity} (confidence: {confidence:.2f})"
        )

        return reflexivity, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate reflexivity for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
