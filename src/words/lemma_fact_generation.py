"""Generation of language-independent lemma facts (stored in ``lemma_facts``)."""

import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.config.lemma_fact_registry import LEMMA_FACT_DEFINITIONS
from storage.crud.lemma_fact import add_lemma_fact, get_lemma_fact_value
from storage.crud.operation_log import log_operation
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def generate_noun_concept_fact(
    client: UnifiedLLMClient, lemma: Lemma, fact_type: str
) -> Tuple[Optional[str], Optional[str], float]:
    """Classify one dimension of the concept, never a language's noun grammar."""
    definition = LEMMA_FACT_DEFINITIONS.get(fact_type)
    if fact_type not in {"individuation", "concreteness"} or definition is None:
        return None, None, 0.0
    if lemma.pos_type not in definition.required_pos:
        return None, None, 0.0

    context = util.prompt_loader.get_context("grammar", fact_type)
    prompt_text = util.prompt_loader.get_prompt("grammar", fact_type).format(
        english_word=lemma.lemma_text,
        disambiguation=lemma.disambiguation or "N/A",
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype or "N/A",
        definition=lemma.definition_text or "N/A",
    )
    schema = Schema(
        name=f"Noun{definition.display_label}Classification",
        description=definition.description,
        properties={
            fact_type: SchemaProperty(
                "string", definition.description, enum=list(definition.allowed_values)
            ),
            "explanation": SchemaProperty("string", "Brief sense-specific explanation"),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )
    try:
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)
    except Exception as error:
        logger.error("Failed to generate %s for %r: %s", fact_type, lemma.lemma_text, error)
        return None, None, 0.0

    result = response.structured_data
    if not result or result.get(fact_type) not in definition.allowed_values:
        logger.error("No usable %s for %r", fact_type, lemma.lemma_text)
        return None, None, 0.0
    return (
        result[fact_type],
        result.get("explanation") or None,
        float(result.get("confidence", 0.5)),
    )


def generate_lemma_fact_for_lemma(
    session: Session,
    client: UnifiedLLMClient,
    config: DataSourceConfig,
    lemma: Lemma,
    fact_type: str,
    min_confidence: float = 0.7,
    skip_existing: bool = True,
    retry_uncertain: bool = False,
) -> Dict[str, Any]:
    """Generate and store one lemma fact; returns a result dict like the grammar-fact path.

    A question a model was uncertain of before (uncertain_llm_results) is
    skipped unless ``retry_uncertain``; an answer below ``min_confidence`` is
    recorded there.
    """
    base: Dict[str, Any] = {"lemma_id": lemma.id, "fact_type": fact_type}

    definition = LEMMA_FACT_DEFINITIONS.get(fact_type)
    if definition is None or not definition.generatable:
        return {**base, "error": f"Unsupported lemma fact type: {fact_type}"}
    if lemma.pos_type not in definition.required_pos:
        return {**base, "error": f"{fact_type} does not apply to {lemma.pos_type}"}

    if skip_existing:
        existing = get_lemma_fact_value(session, lemma.id, fact_type)
        if existing is not None:
            return {**base, "skipped": True, "existing_value": existing}
    if not retry_uncertain and add_lemma_fact.is_uncertain(
        session, lemma_id=lemma.id, fact_type=fact_type
    ):
        return {**base, "skipped": True, "reason": "uncertain"}

    if fact_type not in {"individuation", "concreteness"}:
        return {**base, "error": f"No generator for lemma fact type: {fact_type}"}

    value, notes, confidence = generate_noun_concept_fact(client, lemma, fact_type)
    stored = None
    if value is not None:
        stored = add_lemma_fact(
            session,
            lemma.id,
            fact_type,
            value,
            notes=notes,
            verified=False,
            confidence=confidence,
            min_confidence=min_confidence,
            model=config.model,
        )
    if value is None or confidence < min_confidence:
        session.commit()  # the uncertain row, if one was recorded
        return {
            **base,
            "error": f"Could not generate {fact_type} with sufficient confidence "
            f"(got {confidence:.2f}, need >= {min_confidence})",
            "confidence": confidence,
        }
    if stored is None:
        return {**base, "error": f"Rejected value {value!r} for {fact_type}"}

    log_operation(
        session,
        operation_type="lemma_fact_generated",
        entity_type="lemma_fact",
        entity_id=lemma.id,
        details={
            "fact_type": fact_type,
            "fact_value": value,
            "confidence": confidence,
            "agent": "lape",
            "model": config.model,
        },
    )
    return {**base, "success": True, "fact_value": value, "notes": notes, "confidence": confidence}
