"""
Measure Words Task - Generate Chinese measure words/classifiers for nouns.
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


def generate_measure_words(
    agent: "LapeAgent",
    lemma: Lemma,
    chinese_translation: Optional[str],
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate Chinese measure word(s) for a noun using LLM.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        chinese_translation: The Chinese translation of the word
        session: Database session (optional)

    Returns:
        Tuple of (measure_word, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        logger.warning(
            f"Lemma '{lemma.lemma_text}' is not a noun, skipping measure word generation"
        )
        return None, None, 0.0

    # Load prompts
    try:
        context = util.prompt_loader.get_context("grammar", "measure_words")
        prompt_template = util.prompt_loader.get_prompt("grammar", "measure_words")
    except Exception as e:
        logger.error(f"Failed to load measure_words prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        chinese_translation=chinese_translation,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )

    # Define JSON schema for response
    schema = Schema(
        name="MeasureWordGeneration",
        description="Generate Chinese measure words/classifiers for nouns",
        properties={
            "primary_measure_word": SchemaProperty(
                "string", "The primary/most common measure word"
            ),
            "alternative_measure_words": SchemaProperty(
                "array",
                "List of alternative measure words that can also be used",
                items={"type": "string"},
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation of why this measure word is appropriate"
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

        measure_word = result.get("primary_measure_word", None)
        alternatives = result.get("alternative_measure_words", [])
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        # Combine primary and alternatives for logging
        if alternatives:
            all_measure_words: Optional[str] = f"{measure_word} (alt: {', '.join(alternatives)})"
        else:
            all_measure_words = str(measure_word) if measure_word else None

        logger.info(
            f"Generated measure word for '{lemma.lemma_text}': {all_measure_words} "
            f"(confidence: {confidence:.2f})"
        )

        return measure_word, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate measure word for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
