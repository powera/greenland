"""Grammar-fact generation workflows.

This module implements reusable grammar-fact generation logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from words.workflow_support import build_default_config, get_lemma_or_raise
from sqlalchemy.orm import Session
from storage.backend.config import DataSourceConfig
from storage.config.grammar_fact_registry import legacy_supported_fact_types
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.crud.operation_log import log_operation
from storage.models.schema import Lemma
from storage.translation_helpers import get_translation
from words.grammar_fact_tasks.common import FactResult
from words.grammar_fact_tasks.english_principal_parts import (
    ENGLISH_PRINCIPAL_PARTS_TASK,
    PRINCIPAL_PART_FACT_TYPES,
    generate_and_store_english_principal_parts,
)

logger = logging.getLogger(__name__)

# Supported fact types and their configuration. Keep this historical name for
# Barsukas imports, but source it from the shared registry.
SUPPORTED_FACT_TYPES = legacy_supported_fact_types()


def save_generated_fact(
    session: Session,
    lemma_id: int,
    language_code: str,
    fact_type: str,
    result: FactResult,
    min_confidence: float,
    model: Optional[str],
    via: str = "inline",
) -> str:
    """Store a generated fact if it is good enough and still missing.

    The one writer for generated grammar facts, used by the live path and by
    batch completion alike.  A fact already present -- including one added or
    edited by hand while a batch was out -- is left alone.

    The confidence check is add_grammar_fact's (confidence_gated): an answer
    below *min_confidence* is recorded in uncertain_llm_results, so later
    runs skip the question, and the caller commits that row.

    Returns:
        ``"written"``, ``"rejected"`` (no value, or below *min_confidence*), or
        ``"exists"``.
    """
    if not result.value:
        return "rejected"
    if get_grammar_fact_value(session, lemma_id, language_code, fact_type) is not None:
        return "exists"
    stored = add_grammar_fact(
        session,
        lemma_id=lemma_id,
        language_code=language_code,
        fact_type=fact_type,
        fact_value=result.value,
        notes=result.notes,
        verified=False,
        confidence=result.confidence,
        min_confidence=min_confidence,
        model=model,
    )
    if stored is None:
        return "rejected" if result.confidence < min_confidence else "exists"
    log_operation(
        session,
        operation_type="grammar_fact_generated",
        entity_type="grammar_fact",
        entity_id=lemma_id,
        details={
            "fact_type": fact_type,
            "language_code": language_code,
            "fact_value": result.value,
            "confidence": result.confidence,
            "agent": "lape",
            "model": model,
            "via": via,
        },
    )
    return "written"


def validate_grammar_fact_request(
    lemma: Lemma,
    fact_type: str,
    language_code: str,
    session: Session,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate that grammar fact generation can proceed.

    Args:
        lemma: Lemma to validate
        fact_type: Type of grammar fact
        language_code: Target language code
        session: Database session

    Returns:
        Tuple of (is_valid, error_message, translation)
    """
    if fact_type not in SUPPORTED_FACT_TYPES:
        return False, f"Unsupported fact type: {fact_type}", None

    fact_config = SUPPORTED_FACT_TYPES[fact_type]

    if language_code not in fact_config["languages"]:
        return False, f'Fact type "{fact_type}" does not support language "{language_code}"', None

    if lemma.pos_type not in fact_config["required_pos"]:
        return (
            False,
            f'This word is a {lemma.pos_type}. {fact_type} only works with: {", ".join(fact_config["required_pos"])}',
            None,
        )

    # Get translation for target language
    translation = get_translation(session, lemma, language_code)
    if not translation or not translation.strip():
        return False, f"No {language_code} translation found for this lemma", None

    return True, None, translation


def generate_grammar_fact_for_lemma(
    session: Session,
    lemma: Lemma,
    fact_type: str,
    language_code: str,
    config: Optional[DataSourceConfig] = None,
    min_confidence: float = 0.7,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    """
    Generate a grammar fact for a single lemma.

    This is the core grammar fact generation logic shared by both the workqueue
    handler and the LapeAgent.

    Args:
        session: Database session
        lemma: Lemma to generate fact for
        fact_type: Type of grammar fact to generate
        language_code: Target language code
        config: DataSourceConfig (uses default if not provided)
        min_confidence: Minimum confidence to save the fact
        skip_existing: Skip if fact already exists

    Returns:
        Dictionary with generation results
    """
    if config is None:
        config = build_default_config()

    if fact_type == ENGLISH_PRINCIPAL_PARTS_TASK and language_code != "en":
        return {
            "error": "english_principal_parts only supports language 'en'",
            "lemma_id": lemma.id,
            "fact_type": fact_type,
            "language_code": language_code,
        }
    if language_code == "en" and (
        fact_type == ENGLISH_PRINCIPAL_PARTS_TASK or fact_type in PRINCIPAL_PART_FACT_TYPES
    ):
        from words.grammar_facts import GrammarFactService

        service = GrammarFactService(config=config)
        return generate_and_store_english_principal_parts(
            service,
            session,
            lemma,
            min_confidence=min_confidence,
            skip_existing=skip_existing,
        )

    # Check if fact already exists
    if skip_existing:
        existing_fact = get_grammar_fact_value(session, lemma.id, language_code, fact_type)
        if existing_fact is not None:
            return {
                "skipped": True,
                "reason": "existing",
                "existing_value": existing_fact,
                "lemma_id": lemma.id,
                "fact_type": fact_type,
                "language_code": language_code,
            }

    # Validate request
    is_valid, error, translation = validate_grammar_fact_request(
        lemma, fact_type, language_code, session
    )
    if not is_valid:
        return {
            "error": error,
            "lemma_id": lemma.id,
            "fact_type": fact_type,
            "language_code": language_code,
        }

    # Generate through the shared dispatcher so workqueue and CLI stay aligned.
    assert translation is not None
    from words.grammar_facts import GrammarFactService

    service = GrammarFactService(config=config)
    fact_value, notes, confidence = service.generate_fact(
        fact_type=fact_type,
        lemma=lemma,
        language_code=language_code,
        translation=translation,
        session=session,
    )

    outcome = save_generated_fact(
        session,
        lemma.id,
        language_code,
        fact_type,
        FactResult(fact_value, notes, confidence),
        min_confidence,
        config.model,
    )
    if outcome == "rejected":
        return {
            "error": f"Could not generate {fact_type} with sufficient confidence (got {confidence:.2f}, need >= {min_confidence})",
            "lemma_id": lemma.id,
            "fact_type": fact_type,
            "language_code": language_code,
            "confidence": confidence,
        }
    if outcome == "exists":
        return {
            "skipped": True,
            "reason": "existing",
            "existing_value": get_grammar_fact_value(session, lemma.id, language_code, fact_type),
            "lemma_id": lemma.id,
            "fact_type": fact_type,
            "language_code": language_code,
        }

    return {
        "success": True,
        "lemma_id": lemma.id,
        "fact_type": fact_type,
        "language_code": language_code,
        "fact_value": fact_value,
        "notes": notes,
        "confidence": confidence,
        "translation": translation,
    }


def handle_generate_grammar_fact(session: Session, payload: Dict) -> str:
    """
    Handle grammar fact generation task (workqueue entry point).

    Payload schema:
        lemma_id: int - ID of the lemma to generate fact for
        fact_type: str - Type of grammar fact (e.g., "measure_words", "grammatical_gender")
        language_code: str - Target language code

    Returns:
        str: Result message describing what was generated
    """
    lemma_id = payload["lemma_id"]
    fact_type = payload["fact_type"]
    language_code = payload["language_code"]

    lemma = get_lemma_or_raise(session, lemma_id)

    result = generate_grammar_fact_for_lemma(session, lemma, fact_type, language_code)

    session.commit()

    if result.get("skipped"):
        return f"Skipped: {fact_type} already exists ({result.get('existing_value')})"

    if result.get("error"):
        raise RuntimeError(result["error"])

    return f"Generated {fact_type}: {result['fact_value']} (confidence: {result['confidence']:.2f})"
