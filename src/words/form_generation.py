"""Word-form generation workflows.

This module implements reusable word-form generation logic.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from words.workflow_support import build_default_config, get_lemma_or_raise
from storage.backend.config import DataSourceConfig
from storage.models.schema import Lemma, LemmaTranslation
from storage.translation_helpers import LANGUAGE_FIELDS, get_translation
from wordfreq.translation.client import LinguisticClient
from wordfreq.translation.generate_forms_tasks import get_task_key, process_lemma_for_task

logger = logging.getLogger(__name__)

# Supported language/POS combinations for form generation
SUPPORTED_FORMS = {
    "lt": ["noun", "verb", "adjective", "adverb"],
    "fr": ["noun", "verb"],
    "de": ["noun", "verb"],
    "es": ["noun", "verb"],
    "pt": ["noun", "verb"],
    "en": ["noun", "verb", "adjective", "adverb"],
}


def validate_form_generation_request(
    lemma: Lemma,
    lang_code: str,
    session: Session,
) -> Tuple[bool, Optional[str]]:
    """
    Validate that form generation can proceed for a lemma.

    Args:
        lemma: Lemma to validate
        lang_code: Target language code
        session: Database session

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not lemma.guid:
        return False, "Lemma is missing a GUID"

    pos_type = lemma.pos_type

    if lang_code not in SUPPORTED_FORMS:
        return False, f"Language {lang_code} not supported for form generation"

    if pos_type not in SUPPORTED_FORMS[lang_code]:
        return False, f"POS type {pos_type} not supported for {lang_code}"

    # Check translation exists (except for English)
    if lang_code != "en":
        translation = get_translation(session, lemma, lang_code)
        if not translation or not translation.strip():
            return False, f"No {lang_code} translation found"

    return True, None


def generate_forms_for_lemma(
    session: Session,
    lemma: Lemma,
    lang_code: str,
    config: Optional[DataSourceConfig] = None,
    client: Optional[LinguisticClient] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Generate grammatical forms for a single lemma.

    This is the core form generation logic shared by both the workqueue
    handler and the VilkasAgent.

    Args:
        session: Database session
        lemma: Lemma to generate forms for
        lang_code: Target language code
        config: DataSourceConfig (uses default if not provided)
        client: LinguisticClient (creates one if not provided)

    Returns:
        Tuple of (success, error_message)
    """
    if config is None:
        config = build_default_config()

    # Validate request
    is_valid, error = validate_form_generation_request(lemma, lang_code, session)
    if not is_valid:
        return False, error

    pos_type = lemma.pos_type

    # Get the task key for this language/POS combination
    try:
        task_key = get_task_key(lang_code, pos_type)
    except KeyError:
        return False, f"No form generation task registered for {lang_code} {pos_type}"

    # Create client if not provided
    if client is None:
        client = LinguisticClient(config=config)

    # Generate forms using the task system
    success = process_lemma_for_task(task_key, lemma.id, config, client)

    if success:
        return True, None
    return False, f"Could not generate {lang_code} {pos_type} forms"


def handle_generate_forms(session: Session, payload: Dict) -> str:
    """
    Handle grammatical forms generation task (workqueue entry point).

    Payload schema:
        lemma_id: int - ID of the lemma to generate forms for
        lang_code: str - Language code (default: "lt")

    Returns:
        str: Result message describing what was generated
    """
    lemma_id = payload["lemma_id"]
    lang_code = payload.get("lang_code", "lt")

    lemma = get_lemma_or_raise(session, lemma_id)

    success, error = generate_forms_for_lemma(session, lemma, lang_code)

    session.commit()

    if success:
        return f"Generated {lang_code} {lemma.pos_type} forms"
    raise RuntimeError(error)
