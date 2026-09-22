"""Generate and store the two English verb principal parts as one unit."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Session

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage.crud.operation_log import log_entity_operation
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import Lemma

if TYPE_CHECKING:
    from words.grammar_facts import GrammarFactService

logger = logging.getLogger(__name__)

ENGLISH_PRINCIPAL_PARTS_TASK = "english_principal_parts"
PRINCIPAL_PART_FACT_TYPES = ("past", "past_participle")


@dataclass(frozen=True)
class EnglishPrincipalParts:
    """The stored principal parts returned by one model call."""

    past: str
    past_participle: str
    explanation: str
    confidence: float


def generate_english_principal_parts(
    agent: "GrammarFactService", lemma: Lemma
) -> Optional[EnglishPrincipalParts]:
    """Ask once for an English verb's past and past participle."""
    if lemma.pos_type != "verb":
        return None

    context = util.prompt_loader.get_context("grammar", "english_principal_parts")
    prompt_template = util.prompt_loader.get_prompt("grammar", "english_principal_parts")
    prompt = prompt_template.format(
        verb=lemma.lemma_text,
        definition=lemma.definition_text or "N/A",
        disambiguation=lemma.disambiguation or "N/A",
    )
    schema = Schema(
        name="EnglishVerbPrincipalParts",
        description="Generate the simple past and past participle of one English verb",
        properties={
            "past": SchemaProperty("string", "Canonical simple-past form"),
            "past_participle": SchemaProperty("string", "Canonical past participle"),
            "explanation": SchemaProperty(
                "string", "Brief note about irregularity or sense-dependent usage"
            ),
            "confidence": SchemaProperty(
                "number", "Confidence from 0.0 to 1.0", minimum=0.0, maximum=1.0
            ),
        },
    )

    try:
        response = agent.get_llm_client().generate_chat(
            prompt=prompt,
            json_schema=schema,
            context=context,
        )
    except Exception as error:
        logger.error("Failed to generate principal parts for %s: %s", lemma.lemma_text, error)
        return None
    result = response.structured_data
    if not result:
        return None

    past = str(result.get("past", "")).strip()
    past_participle = str(result.get("past_participle", "")).strip()
    if not past or not past_participle:
        return None
    if "\n" in past or "\n" in past_participle:
        return None

    return EnglishPrincipalParts(
        past=past,
        past_participle=past_participle,
        explanation=str(result.get("explanation", "")).strip(),
        confidence=float(result.get("confidence", 0.5)),
    )


def principal_parts_coverage(session: Session, lemma: Lemma) -> dict[str, Optional[str]]:
    """Return the two stored values for a verb, with ``None`` for gaps."""
    rows = (
        session.query(GrammarFact)
        .filter(
            GrammarFact.lemma_id == lemma.id,
            GrammarFact.language_code == "en",
            GrammarFact.fact_type.in_(PRINCIPAL_PART_FACT_TYPES),
        )
        .all()
    )
    values: dict[str, Optional[str]] = {fact_type: None for fact_type in PRINCIPAL_PART_FACT_TYPES}
    for row in rows:
        values[row.fact_type] = row.fact_value
    return values


def generate_and_store_english_principal_parts(
    agent: "GrammarFactService",
    session: Session,
    lemma: Lemma,
    *,
    min_confidence: float = 0.7,
    skip_existing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate both facts and persist them in one transaction."""
    if lemma.pos_type != "verb":
        return {"skipped": True, "reason": "not_a_verb", "lemma_id": lemma.id}

    existing = principal_parts_coverage(session, lemma)
    if skip_existing and all(existing.values()):
        return {
            "skipped": True,
            "reason": "existing",
            "lemma_id": lemma.id,
            "past": existing["past"],
            "past_participle": existing["past_participle"],
        }

    generated = generate_english_principal_parts(agent, lemma)
    if generated is None or generated.confidence < min_confidence:
        confidence = generated.confidence if generated is not None else 0.0
        return {
            "error": "Could not generate both principal parts with sufficient confidence",
            "lemma_id": lemma.id,
            "confidence": confidence,
        }

    generated_values = {
        "past": generated.past,
        "past_participle": generated.past_participle,
    }
    if not dry_run:
        stored_types: list[str] = []
        for fact_type, fact_value in generated_values.items():
            row = (
                session.query(GrammarFact)
                .filter(
                    GrammarFact.lemma_id == lemma.id,
                    GrammarFact.language_code == "en",
                    GrammarFact.fact_type == fact_type,
                )
                .one_or_none()
            )
            if row is not None and skip_existing:
                continue
            if row is None:
                row = GrammarFact(
                    lemma_id=lemma.id,
                    language_code="en",
                    fact_type=fact_type,
                )
                session.add(row)
            row.fact_value = fact_value
            row.notes = generated.explanation or "Generated by Lape English principal parts"
            row.verified = False
            stored_types.append(fact_type)

        log_entity_operation(
            session,
            source="words/english-principal-parts",
            operation_type="grammar_fact_update",
            entity_guid=lemma.guid,
            lemma_id=lemma.id,
            fact={
                "language_code": "en",
                "changed_fields": stored_types,
                "past": generated.past,
                "past_participle": generated.past_participle,
                "confidence": generated.confidence,
                "model": agent.config.model,
            },
        )
        session.commit()

    return {
        "lemma_id": lemma.id,
        "lemma_text": lemma.lemma_text,
        "translation": lemma.lemma_text,
        "past": generated.past,
        "past_participle": generated.past_participle,
        "fact_value": f"{generated.past} / {generated.past_participle}",
        "notes": generated.explanation,
        "confidence": generated.confidence,
        "dry_run": dry_run,
    }
