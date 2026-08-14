"""
Grammatical Gender Task - Determine grammatical gender for nouns.
"""

import logging
from typing import List, Optional, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage.models.schema import Lemma

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)


def generate_grammatical_gender(
    agent: "GrammarFactService",
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate grammatical gender for a noun using LLM.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        target_translation: The translation in the target language
        language_code: Target language code (e.g., 'fr', 'lt', 'de')
        session: Database session (optional)

    Returns:
        Tuple of (gender, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping gender generation")
        return None, None, 0.0

    if language_code not in agent.GENDER_SYSTEMS:
        logger.error(f"Language '{language_code}' does not have a configured gender system")
        return None, None, 0.0

    gender_config = agent.GENDER_SYSTEMS[language_code]
    language_name = gender_config["name"]
    valid_genders = ", ".join(gender_config["genders"])
    gender_system = gender_config["description"]

    # Load prompts
    try:
        context = util.prompt_loader.get_context("grammar", "gender")
        prompt_template = util.prompt_loader.get_prompt("grammar", "gender")
    except Exception as e:
        logger.error(f"Failed to load grammatical_gender prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
        language_name=language_name,
        language_code=language_code,
        gender_system=gender_system,
        valid_genders=valid_genders,
    )

    # Define JSON schema for response
    schema = Schema(
        name="GrammaticalGenderGeneration",
        description=f"Determine grammatical gender for {language_name} nouns",
        properties={
            "gender": SchemaProperty(
                "string",
                f"The grammatical gender: {valid_genders}",
                enum=list(gender_config["genders"]),
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation of why this gender is correct"
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

        # Extract structured data
        if response.structured_data:
            result = response.structured_data
        else:
            logger.error(f"No structured data received for '{lemma.lemma_text}'")
            return None, None, 0.0

        gender = result.get("gender", None)
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        logger.info(
            f"Generated gender for '{lemma.lemma_text}' ({target_translation}): "
            f"{gender} (confidence: {confidence:.2f})"
        )

        return gender, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate gender for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
