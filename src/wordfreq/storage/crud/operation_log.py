#!/usr/bin/python3

"""CRUD operations for OperationLog model."""

import json
from typing import Optional

from wordfreq.storage.models.operation_log import OperationLog


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
