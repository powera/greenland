#!/usr/bin/python3

"""CRUD operations for OperationLog model."""

import json
from typing import Optional

from wordfreq.storage.models.operation_log import OperationLog


def log_operation(
    session,
    operation_type: str,
    source: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[dict] = None,
    fact: Optional[dict] = None,
    lemma_id: Optional[int] = None,
    word_token_id: Optional[int] = None,
    derivative_form_id: Optional[int] = None,
    **extra_data
) -> OperationLog:
    """
    Log a general operation to the operation log.

    This is a flexible logging function that can handle various operation types.

    Args:
        session: Database session
        operation_type: Type of operation (e.g., "grammar_fact_generated", "definition_update")
        source: Source of the operation (e.g., "lape-agent", "barsukas-web-interface")
        entity_type: Type of entity being operated on (e.g., "grammar_fact", "lemma")
        entity_id: ID of the entity being operated on
        details: Dictionary of operation details (alternative to fact)
        fact: Dictionary of fact data (alternative to details)
        lemma_id: ID of the lemma being modified
        word_token_id: Optional word token ID
        derivative_form_id: Optional derivative form ID
        **extra_data: Additional data to include in the fact JSON

    Returns:
        OperationLog object that was created
    """
    # Determine source - if not provided, try to infer from details/fact
    if source is None:
        if details and 'source' in details:
            source = details['source']
        elif fact and isinstance(fact, dict) and 'source' in fact:
            source = fact['source']
        else:
            source = "unknown"

    # Build the fact JSON - use whichever was provided (details or fact)
    fact_data = details or fact or {}

    # Add entity type if provided
    if entity_type:
        fact_data['entity_type'] = entity_type

    # Add entity_id if provided and not already in lemma_id
    if entity_id and not lemma_id:
        lemma_id = entity_id

    # Add any extra data provided
    fact_data.update(extra_data)

    # Remove None values to keep JSON compact
    fact_data = {k: v for k, v in fact_data.items() if v is not None}

    # Create operation log entry
    log_entry = OperationLog(
        source=source,
        operation_type=operation_type,
        fact=json.dumps(fact_data),
        lemma_id=lemma_id,
        word_token_id=word_token_id,
        derivative_form_id=derivative_form_id
    )

    session.add(log_entry)
    session.flush()
    return log_entry


def log_translation_change(
    session,
    source: str,
    operation_type: str,
    lemma_id: Optional[int] = None,
    language_code: Optional[str] = None,
    old_translation: Optional[str] = None,
    new_translation: Optional[str] = None,
    word_token_id: Optional[int] = None,
    derivative_form_id: Optional[int] = None,
    **extra_data
) -> OperationLog:
    """
    Log a translation change operation.

    Args:
        session: Database session
        source: Source of the operation (e.g., "voras-agent", "gpt-5-mini", "manual-import")
        operation_type: Type of operation (e.g., "translation", "definition", "import")
        lemma_id: ID of the lemma being modified
        language_code: Language code of the translation (e.g., "fr", "es", "de")
        old_translation: Previous translation value (None for new translations)
        new_translation: New translation value (None for deletions)
        word_token_id: Optional word token ID
        derivative_form_id: Optional derivative form ID
        **extra_data: Additional data to include in the fact JSON

    Returns:
        OperationLog object that was created
    """
    # Build the fact JSON
    fact_data = {
        "language_code": language_code,
        "old_translation": old_translation,
        "new_translation": new_translation,
    }

    # Add any extra data provided
    fact_data.update(extra_data)

    # Remove None values to keep JSON compact
    fact_data = {k: v for k, v in fact_data.items() if v is not None}

    # Create operation log entry
    log_entry = OperationLog(
        source=source,
        operation_type=operation_type,
        fact=json.dumps(fact_data),
        lemma_id=lemma_id,
        word_token_id=word_token_id,
        derivative_form_id=derivative_form_id
    )

    session.add(log_entry)
    session.flush()
    return log_entry
