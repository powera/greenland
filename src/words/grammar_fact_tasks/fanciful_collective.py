"""
Fanciful Collective Task - Generate ornamental English collective nouns for animals.

These are terms of venery ("a murder of crows", "a parliament of owls"): tied to
one specific animal and decorative rather than load-bearing, since the ordinary
collective ("a flock of crows") is always acceptable. Generic collectives that
range across many animals - flock, herd, swarm - are ordinary vocabulary and live
as their own lemmas instead.
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


def prepare_fanciful_collective(
    session: Optional[Session], lemma: Lemma, translation: Optional[str], language_code: str
) -> Union[LLMCall, FactResult]:
    """Build the fanciful-collective request (English; translation unused)."""
    if lemma.pos_type != "noun":
        logger.warning(
            f"Lemma '{lemma.lemma_text}' is not a noun, skipping fanciful collective generation"
        )
        return NO_FACT

    context, prompt_template = load_prompt("fanciful_collective")
    prompt_text = prompt_template.format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        definition=lemma.definition_text or "N/A",
    )
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
    return LLMCall(prompt=prompt_text, schema=schema, context=context)


def interpret_fanciful_collective(
    data: Dict[str, Any], translation: Optional[str], language_code: str
) -> FactResult:
    """Most animals have no term; that is a normal answer, stored as nothing."""
    collective = data.get("primary_collective", None)
    alternatives = data.get("alternative_collectives", [])
    explanation = data.get("explanation", "")
    confidence = float(data.get("confidence", 0.5))

    # No term for this animal is the common case, not an error. Report zero
    # confidence so the caller's threshold check stores nothing.
    if not collective:
        return FactResult(None, explanation, 0.0)

    # The unique constraint allows one fact per (lemma, language, fact_type),
    # so alternatives ride along in the notes rather than the value.
    if alternatives:
        explanation = f"{explanation} (alt: {', '.join(alternatives)})".strip()
    return FactResult(collective, explanation, confidence)


TASK = FactTask(prepare_fanciful_collective, interpret_fanciful_collective)


def generate_fanciful_collective(
    agent: "GrammarFactService", lemma: Lemma, session: Optional[Session] = None
) -> Tuple[Optional[str], Optional[str], float]:
    """Generate the ornamental English collective noun for an animal using an LLM.

    Most animals have no such term, so returning None is a normal, correct
    outcome rather than a failure - grammar facts store only positive assertions.

    Returns:
        Tuple of (collective, explanation, confidence)
    """
    return run_live(agent, TASK, session, lemma, None, "en", "fanciful collective")
