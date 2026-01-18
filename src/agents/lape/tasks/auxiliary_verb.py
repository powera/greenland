"""
Auxiliary Verb Task - Determine auxiliary verb for compound tenses.
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


def generate_auxiliary_verb(
    agent: "LapeAgent",
    lemma: Lemma,
    target_translation: Optional[str],
    language_code: str,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate auxiliary verb classification for compound tenses using LLM.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        target_translation: The translation in the target language
        language_code: Target language code (fr, de, it)
        session: Database session (optional)

    Returns:
        Tuple of (auxiliary_verb, explanation, confidence)
    """
    if lemma.pos_type != "verb":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a verb, skipping auxiliary")
        return None, None, 0.0

    if language_code not in agent.AUXILIARY_SYSTEMS:
        logger.error(f"Language '{language_code}' does not have auxiliary verb configuration")
        return None, None, 0.0

    aux_config = agent.AUXILIARY_SYSTEMS[language_code]
    language_name = aux_config["name"]
    valid_auxiliaries = ", ".join(aux_config["auxiliaries"])

    # Load prompts
    try:
        context = util.prompt_loader.get_context("wordfreq", "auxiliary_verb")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "auxiliary_verb")
    except Exception as e:
        logger.error(f"Failed to load auxiliary_verb prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        target_translation=target_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
        language_name=language_name,
        language_code=language_code,
        valid_auxiliaries=valid_auxiliaries,
    )

    # Define JSON schema for response
    schema = Schema(
        name="AuxiliaryVerbClassification",
        description=f"Classify auxiliary verb for {language_name} compound tenses",
        properties={
            "auxiliary_verb": SchemaProperty(
                "string",
                f"The auxiliary verb: {valid_auxiliaries}",
                enum=list(aux_config["auxiliaries"]),
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

        auxiliary = result.get("auxiliary_verb", None)
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        logger.info(
            f"Generated auxiliary for '{lemma.lemma_text}' ({target_translation}): "
            f"{auxiliary} (confidence: {confidence:.2f})"
        )

        return auxiliary, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate auxiliary for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
