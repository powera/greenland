"""Workqueue handler for pronunciation tasks.

This module implements the core pronunciation generation logic that is shared
between the Barsukas task worker and the PapugaAgent CLI.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from agents.common.wq_tools import build_default_config, get_lemma_or_raise
import constants
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.models.schema import (
    DerivativeForm,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.tools.llm_validators import generate_pronunciation

logger = logging.getLogger(__name__)


def get_example_sentence_for_lemma(session, lemma_id: int) -> Optional[str]:
    """
    Get an example English sentence containing the lemma.

    Args:
        session: Database session
        lemma_id: ID of the lemma

    Returns:
        Example sentence text or None if not found
    """
    example_translation = (
        session.query(SentenceTranslation)
        .join(Sentence)
        .join(SentenceWord)
        .filter(
            SentenceWord.lemma_id == lemma_id,
            SentenceTranslation.language_code == "en",
        )
        .first()
    )
    return example_translation.translation_text if example_translation else None


def generate_pronunciation_for_form(
    form: DerivativeForm,
    pos_type: str,
    definition: Optional[str],
    example_sentence: Optional[str],
    model: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Generate pronunciation for a single derivative form.

    Args:
        form: DerivativeForm to generate pronunciation for
        pos_type: Part of speech type
        definition: English definition
        example_sentence: Example sentence for context
        model: LLM model to use (defaults to constants.DEFAULT_MODEL)

    Returns:
        Tuple of (success, ipa_pronunciation, phonetic_pronunciation)
    """
    if model is None:
        model = constants.DEFAULT_MODEL

    result = generate_pronunciation(
        word=form.derivative_form_text,
        pos_type=pos_type,
        definition=definition,
        example_sentence=example_sentence,
        model=model,
    )

    ipa = result.get("ipa_pronunciation")
    phonetic = result.get("phonetic_pronunciation")

    success = bool(ipa or phonetic)
    return success, ipa, phonetic


def generate_pronunciations_for_lemma(
    session,
    lemma: Lemma,
    lang_code: str = "en",
    config: Optional[DataSourceConfig] = None,
) -> Tuple[int, List[str]]:
    """
    Generate pronunciations for all forms of a lemma missing them.

    This is the core pronunciation generation logic shared by both the workqueue
    handler and the PapugaAgent.

    Args:
        session: Database session
        lemma: Lemma to generate pronunciations for
        lang_code: Language code (default: "en")
        config: DataSourceConfig (uses default if not provided)

    Returns:
        Tuple of (generated_count, list of error messages)
    """
    if config is None:
        config = build_default_config()

    # Find forms missing pronunciations
    forms_missing_pronunciations = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.lemma_id == lemma.id,
            DerivativeForm.language_code == lang_code,
            DerivativeForm.ipa_pronunciation.is_(None),
            DerivativeForm.phonetic_pronunciation.is_(None),
        )
        .all()
    )

    if not forms_missing_pronunciations:
        return 0, []

    # Get example sentence for context
    example_text = get_example_sentence_for_lemma(session, lemma.id)

    generated_count = 0
    errors = []

    for form in forms_missing_pronunciations:
        success, ipa, phonetic = generate_pronunciation_for_form(
            form=form,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text,
            example_sentence=example_text,
            model=config.model,
        )

        if ipa:
            form.ipa_pronunciation = ipa
        if phonetic:
            form.phonetic_pronunciation = phonetic

        if success:
            generated_count += 1
        else:
            errors.append(f"No pronunciation generated for '{form.derivative_form_text}'")

    return generated_count, errors


def handle_generate_pronunciations(session, payload: Dict) -> str:
    """
    Handle pronunciation generation task (workqueue entry point).

    Payload schema:
        lemma_id: int - ID of the lemma to generate pronunciations for
        lang_code: str - Language code (default: "en")

    Returns:
        str: Result message describing what was generated
    """
    lemma_id = payload["lemma_id"]
    lang_code = payload.get("lang_code", "en")

    lemma = get_lemma_or_raise(session, lemma_id)

    generated_count, errors = generate_pronunciations_for_lemma(
        session, lemma, lang_code
    )

    session.commit()

    if generated_count == 0 and not errors:
        return f"No missing pronunciations for {lang_code} forms"
    if generated_count == 0 and errors:
        raise RuntimeError("; ".join(errors))

    return f"Generated pronunciations for {generated_count} form(s)"
