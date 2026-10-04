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


def generate_has_individual_instances(
    client: UnifiedLLMClient, lemma: Lemma
) -> Tuple[Optional[str], Optional[str], float]:
    """Classify natural individual instances of a lemma sense."""
    if lemma.pos_type != "noun":
        logger.warning(f"Lemma '{lemma.lemma_text}' is not a noun, skipping individual instances")
        return None, None, 0.0

    context = util.prompt_loader.get_context("grammar", "has_individual_instances")
    prompt_text = util.prompt_loader.get_prompt("grammar", "has_individual_instances").format(
        english_word=lemma.lemma_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype or "N/A",
        definition=lemma.definition_text or "N/A",
    )
    schema = Schema(
        name="NounIndividualInstancesClassification",
        description="Classify whether a lemma sense has natural individual instances",
        properties={
            "has_individual_instances": SchemaProperty(
                "boolean", "Whether the sense denotes naturally separate individual instances"
            ),
            "explanation": SchemaProperty("string", "Brief explanation if notable"),
            "confidence": SchemaProperty(
                "number", "Confidence score 0.0-1.0", minimum=0.0, maximum=1.0
            ),
        },
    )

    try:
        response = client.generate_chat(prompt=prompt_text, json_schema=schema, context=context)
    except Exception as error:
        logger.error(f"Failed to generate individual instances for '{lemma.lemma_text}': {error}")
        return None, None, 0.0

    result = response.structured_data
    if not result or not isinstance(result.get("has_individual_instances"), bool):
        logger.error(f"No usable structured data for '{lemma.lemma_text}'")
        return None, None, 0.0

    value = "true" if result["has_individual_instances"] else "false"
    return value, result.get("explanation") or None, float(result.get("confidence", 0.5))


def generate_lemma_fact_for_lemma(
    session: Session,
    client: UnifiedLLMClient,
    config: DataSourceConfig,
    lemma: Lemma,
    fact_type: str,
    min_confidence: float = 0.7,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    """Generate and store one lemma fact; returns a result dict like the grammar-fact path."""
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

    if fact_type != "has_individual_instances":
        return {**base, "error": f"No generator for lemma fact type: {fact_type}"}

    value, notes, confidence = generate_has_individual_instances(client, lemma)
    if value is None or confidence < min_confidence:
        return {
            **base,
            "error": f"Could not generate {fact_type} with sufficient confidence "
            f"(got {confidence:.2f}, need >= {min_confidence})",
            "confidence": confidence,
        }

    if add_lemma_fact(session, lemma.id, fact_type, value, notes=notes, verified=False) is None:
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
