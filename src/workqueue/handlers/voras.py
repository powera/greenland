"""Workqueue handler for translation tasks.

This module implements the core translation generation logic that is shared
between the Barsukas task worker and the VorasAgent CLI.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from workqueue.tools import build_default_config, get_lemma_or_raise
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import (
    LANGUAGE_FIELDS,
    LANGUAGE_NAMES,
    convert_llm_response_to_lang_codes,
    get_reference_translation,
    get_translation,
    set_translation,
)
from wordfreq.storage.crud.operation_log import log_translation_change
from wordfreq.translation.client import LinguisticClient

logger = logging.getLogger(__name__)


def generate_missing_translations_for_lemma(
    session: Session,
    lemma: Lemma,
    config: Optional[DataSourceConfig] = None,
    source: Optional[str] = None,
) -> Tuple[int, List[str]]:
    """
    Generate missing translations for a single lemma.

    This is the core translation generation logic shared by both the workqueue
    handler and the VorasAgent.

    Args:
        session: Database session
        lemma: Lemma to generate translations for
        config: DataSourceConfig (uses default if not provided)
        source: Source identifier for operation logging

    Returns:
        Tuple of (added_count, list of error messages)
    """
    if config is None:
        config = build_default_config()

    if source is None:
        source = f"voras-agent/{config.model}"

    # Find missing languages for this lemma
    missing_languages = []
    for lc in LANGUAGE_FIELDS.keys():
        translation = get_translation(session, lemma, lc)
        if not translation or not translation.strip():
            missing_languages.append(lc)

    if not missing_languages:
        return 0, []

    # Filter out English (can't generate)
    missing_languages = [lc for lc in missing_languages if lc != "en"]
    if not missing_languages:
        return 0, []

    # Get reference translation
    reference_lang_code, reference_translation = get_reference_translation(
        session, lemma, exclude_languages=missing_languages
    )

    # Fall back to English if no reference
    if not reference_translation:
        reference_lang_code = "en"
        reference_translation = lemma.lemma_text

    # Build list of language names for LLM query
    missing_lang_names = [
        LANGUAGE_NAMES[lc].lower() for lc in missing_languages if lc in LANGUAGE_NAMES
    ]

    # Query LLM for translations
    client = LinguisticClient(model=config.model, db_path=config.sqlite_path, debug=config.debug)
    llm_response, success = client.query_translations(
        english_word=lemma.lemma_text,
        reference_translation=(reference_lang_code, reference_translation),
        definition=lemma.definition_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        languages=missing_lang_names,
    )

    if not success or not llm_response:
        return 0, ["LLM could not generate translations"]

    # Convert LLM response to lang_code format and save
    translations_by_lang_code = convert_llm_response_to_lang_codes(llm_response)

    added_count = 0
    errors = []
    for lang_code in missing_languages:
        translation = translations_by_lang_code.get(lang_code, "").strip()
        if translation:
            old_translation, new_translation = set_translation(
                session, lemma, lang_code, translation
            )
            log_translation_change(
                session=session,
                source=source,
                operation_type="translation",
                lemma_id=lemma.id,
                language_code=lang_code,
                old_translation=old_translation,
                new_translation=new_translation,
            )
            added_count += 1
        else:
            lang_name = LANGUAGE_NAMES.get(lang_code, lang_code)
            errors.append(f"Empty {lang_name} translation returned")

    return added_count, errors


def handle_add_missing_translations(session: Session, payload: Dict) -> str:
    """
    Handle missing translations task (workqueue entry point).

    Payload schema:
        lemma_id: int - ID of the lemma to generate translations for

    Returns:
        str: Result message describing what was generated
    """
    lemma_id = payload["lemma_id"]
    lemma = get_lemma_or_raise(session, lemma_id)

    added_count, errors = generate_missing_translations_for_lemma(session, lemma)

    if errors and added_count == 0:
        raise RuntimeError("; ".join(errors))

    session.commit()

    if added_count == 0:
        return "No missing translations to generate"
    return f"Added {added_count} translation(s)"
