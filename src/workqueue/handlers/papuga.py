"""Workqueue handler for pronunciation tasks.

This module implements the core pronunciation generation logic that is shared
between the Barsukas task worker and the PapugaAgent CLI.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import case
from sqlalchemy.orm import Session

from workqueue.tools import build_default_config, get_lemma_or_raise
import constants
from storage.backend.config import DataSourceConfig
from storage.crud.derivative_form import add_derivative_form, needs_pronunciation_update_filter
from storage.models.schema import (
    DerivativeForm,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
)
from storage.translation_helpers import (
    LANGUAGE_FIELDS,
    get_translation,
    get_translation_pronunciations,
    set_translation_pronunciations,
)
from wordfreq.tools.llm_validators import generate_pronunciation

logger = logging.getLogger(__name__)


def _get_default_base_grammatical_form(pos_type: str) -> str:
    """Return a sensible grammatical-form label for a synthetic base form."""
    default_forms = {
        "verb": "infinitive",
        "noun": "singular",
        "adjective": "positive",
        "adverb": "positive",
    }
    return default_forms.get(pos_type, "lemma")


def get_example_sentence_for_lemma(session: Session, lemma_id: int) -> Optional[str]:
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
    english_translation: Optional[str] = None,
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
        language_code=form.language_code,
        grammatical_form=form.grammatical_form,
        english_translation=english_translation,
    )

    ipa = result.get("ipa_pronunciation")
    phonetic = result.get("phonetic_pronunciation")

    success = bool(ipa or phonetic)
    return success, ipa, phonetic


def generate_pronunciations_for_lemma(
    session: Session,
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

    translation_text = get_translation(session, lemma, lang_code)
    translation_ipa, translation_phonetic = get_translation_pronunciations(
        session, lemma, lang_code
    )
    existing_base_form = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.lemma_id == lemma.id,
            DerivativeForm.language_code == lang_code,
            DerivativeForm.is_base_form == True,
        )
        .order_by(
            case(
                (
                    DerivativeForm.derivative_form_text == translation_text,
                    0,
                ),
                else_=1,
            ),
            DerivativeForm.id,
        )
        .first()
    )
    supports_translation_pronunciations = LANGUAGE_FIELDS.get(lang_code, (None, None, False))[2]
    translation_missing = bool(
        supports_translation_pronunciations
        and translation_text
        and (not translation_ipa or not translation_phonetic)
    )
    needs_english_lemma_pronunciation = bool(
        lang_code == "en" and translation_text and existing_base_form is None
    )

    # Find forms missing pronunciations
    forms_missing_pronunciations = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.lemma_id == lemma.id,
            DerivativeForm.language_code == lang_code,
            needs_pronunciation_update_filter(),
        )
        .all()
    )

    if (
        not forms_missing_pronunciations
        and not translation_missing
        and not needs_english_lemma_pronunciation
    ):
        return 0, []

    # Get example sentence for context
    example_text = get_example_sentence_for_lemma(session, lemma.id)

    generated_count = 0
    errors: List[str] = []

    for form in forms_missing_pronunciations:
        success, ipa, phonetic = generate_pronunciation_for_form(
            form=form,
            pos_type=lemma.pos_type,
            definition=lemma.definition_text,
            example_sentence=example_text,
            english_translation=lemma.lemma_text if lang_code != "en" else None,
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

    if translation_missing and translation_text:
        ipa_value = translation_ipa or (
            existing_base_form.ipa_pronunciation if existing_base_form else None
        )
        phonetic_value = translation_phonetic or (
            existing_base_form.phonetic_pronunciation if existing_base_form else None
        )

        if not ipa_value or not phonetic_value:
            success, generated_ipa, generated_phonetic = generate_pronunciation_for_form(
                form=DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text=translation_text,
                    language_code=lang_code,
                    grammatical_form="lemma_translation",
                    is_base_form=True,
                ),
                pos_type=lemma.pos_type,
                definition=lemma.definition_text,
                example_sentence=example_text,
                english_translation=lemma.lemma_text if lang_code != "en" else None,
                model=config.model,
            )
            if success:
                ipa_value = generated_ipa or ipa_value
                phonetic_value = generated_phonetic or phonetic_value
            else:
                errors.append(
                    f"No pronunciation generated for lemma translation '{translation_text}'"
                )

        if ipa_value or phonetic_value:
            set_translation_pronunciations(
                session,
                lemma,
                lang_code,
                ipa_pronunciation=ipa_value,
                phonetic_pronunciation=phonetic_value,
            )
            generated_count += 1

    if needs_english_lemma_pronunciation and translation_text:
        success, generated_ipa, generated_phonetic = generate_pronunciation_for_form(
            form=DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text=translation_text,
                language_code=lang_code,
                grammatical_form=_get_default_base_grammatical_form(lemma.pos_type),
                is_base_form=True,
            ),
            pos_type=lemma.pos_type,
            definition=lemma.definition_text,
            example_sentence=example_text,
            english_translation=None,
            model=config.model,
        )
        if success:
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=translation_text,
                language_code=lang_code,
                grammatical_form=_get_default_base_grammatical_form(lemma.pos_type),
                is_base_form=True,
                ipa_pronunciation=generated_ipa,
                phonetic_pronunciation=generated_phonetic,
            )
            generated_count += 1
        else:
            errors.append(f"No pronunciation generated for lemma '{translation_text}'")

    return generated_count, errors


def handle_generate_pronunciations(session: Session, payload: Dict) -> str:
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

    generated_count, errors = generate_pronunciations_for_lemma(session, lemma, lang_code)

    session.commit()

    if generated_count == 0 and not errors:
        return f"No missing pronunciations for {lang_code} forms"
    if generated_count == 0 and errors:
        raise RuntimeError("; ".join(errors))

    return f"Generated pronunciations for {generated_count} form(s)"
