"""
Fanciful Collective Task - Generate ornamental English collective nouns for animals.

These are terms of venery ("a murder of crows", "a parliament of owls"): tied to
one specific animal and decorative rather than load-bearing, since the ordinary
collective ("a flock of crows") is always acceptable. Generic collectives that
range across many animals - flock, herd, swarm - are ordinary vocabulary and live
as their own lemmas instead.
"""

import logging
from typing import Optional, Tuple, TYPE_CHECKING

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage.models.schema import Lemma

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)


def generate_fanciful_collective(
    agent: "GrammarFactService",
    lemma: Lemma,
    session: Optional[Session] = None,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Generate the ornamental English collective noun for an animal using an LLM.

    Most animals have no such term, so returning None is a normal, correct
    outcome rather than a failure - grammar facts store only positive assertions.

    Args:
        agent: The LapeAgent instance
        lemma: The Lemma object
        session: Database session (optional)

    Returns:
        Tuple of (fanciful_collective, explanation, confidence)
    """
    if lemma.pos_type != "noun":
        logger.warning(
            f"Lemma '{lemma.lemma_text}' is not a noun, skipping fanciful collective generation"
        )
        return None, None, 0.0

    # Load prompts
    try:
        context = util.prompt_loader.get_context("grammar", "fanciful_collective")
        prompt_template = util.prompt_loader.get_prompt("grammar", "fanciful_collective")
    except Exception as e:
        logger.error(f"Failed to load fanciful_collective prompts: {e}")
        return None, None, 0.0

    # Format prompt
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )

    # Define JSON schema for response
    schema = Schema(
        name="FancifulCollectiveGeneration",
        description="Generate the ornamental English collective noun for an animal",
        properties={
            "primary_collective": SchemaProperty(
                "string",
                "The primary fanciful collective noun, bare term only; omit if none exists",
                required=False,
            ),
            "alternative_collectives": SchemaProperty(
                "array",
                "Other well-attested fanciful collective nouns for this animal",
                required=False,
                items={"type": "string"},
            ),
            "explanation": SchemaProperty(
                "string", "Brief explanation of the term's status and how commonly it is used"
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

        collective = result.get("primary_collective", None)
        alternatives = result.get("alternative_collectives", [])
        explanation = result.get("explanation", "")
        confidence = float(result.get("confidence", 0.5))

        # No term for this animal is the common case, not an error. Report zero
        # confidence so the caller's threshold check stores nothing.
        if not collective:
            logger.info(f"No fanciful collective for '{lemma.lemma_text}'")
            return None, explanation, 0.0

        # The unique constraint allows one fact per (lemma, language, fact_type),
        # so alternatives ride along in the notes rather than the value.
        if alternatives:
            explanation = f"{explanation} (alt: {', '.join(alternatives)})".strip()

        logger.info(
            f"Generated fanciful collective for '{lemma.lemma_text}': {collective} "
            f"(confidence: {confidence:.2f})"
        )

        return collective, explanation, confidence

    except Exception as e:
        logger.error(f"Failed to generate fanciful collective for '{lemma.lemma_text}': {e}")
        return None, None, 0.0
