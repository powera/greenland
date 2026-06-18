"""Capability handlers for word translation tasks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import constants
from agents.voras.agent import VorasAgent
from barsukas.config import Config
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.operation_log import log_operation
from storage.models.schema import Lemma
from storage.translation_helpers import (
    LANGUAGE_FIELDS,
    convert_llm_response_to_translation_metadata,
    get_reference_translation,
    get_translation,
    lang_code_to_llm_field,
    normalize_llm_language_codes,
    split_llm_language_batches,
)
from wordfreq.translation.client import LinguisticClient
from workqueue.tools import workqueue_payload_handler


def _build_config(model: Optional[str] = None) -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=model or constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )


def do_generate_missing_translations(
    session: Any,
    lemma_id: int,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate missing translations for a lemma, optionally constrained to languages."""
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    requested_languages = normalize_llm_language_codes(
        languages or list(LANGUAGE_FIELDS.keys()),
        operation_name="Workqueue word translation",
        max_languages=len(LANGUAGE_FIELDS),
    )
    missing_languages: List[str] = []
    for language_code in requested_languages:
        translation = get_translation(session, lemma, language_code)
        if not translation or not translation.strip():
            missing_languages.append(language_code)

    if not missing_languages:
        return "No missing translations to generate"

    reference_lang_code, reference_translation = get_reference_translation(
        session, lemma, exclude_languages=missing_languages
    )
    if not reference_translation:
        reference_lang_code = "en"
        reference_translation = lemma.lemma_text

    config = _build_config(model)
    agent = VorasAgent(config=config)
    client = LinguisticClient(
        model=config.model or "",
        db_path=config.sqlite_path or "",
        debug=Config.DEBUG,
    )
    translations: Dict[str, Any] = {}
    for language_batch in split_llm_language_batches(missing_languages):
        batch_translations, success = client.query_translations(
            english_word=lemma.lemma_text,
            reference_translation=(
                reference_lang_code or "en",
                reference_translation or lemma.lemma_text,
            ),
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            languages=language_batch,
        )
        if not success or not batch_translations:
            raise RuntimeError(
                "LLM could not generate translations for " + ", ".join(language_batch)
            )
        translations.update(batch_translations)

    translation_metadata_by_lang_code = convert_llm_response_to_translation_metadata(translations)
    added_count = 0
    for language_code in missing_languages:
        llm_field = lang_code_to_llm_field(language_code)
        if llm_field:
            response_value = translations.get(llm_field, "")
            if isinstance(response_value, dict):
                raw_translation = response_value.get("translation", "")
                translation_text = (
                    raw_translation.strip() if isinstance(raw_translation, str) else ""
                )
            else:
                translation_text = response_value.strip() if isinstance(response_value, str) else ""
            if translation_text:
                translation_metadata = translation_metadata_by_lang_code.get(language_code, {})
                agent.set_translation(
                    session,
                    lemma,
                    language_code,
                    translation_text,
                    translation_status=translation_metadata.get("translation_status"),
                    translation_status_note=translation_metadata.get("translation_status_note"),
                )
                added_count += 1

    log_operation(
        session,
        operation_type="translations_populated",
        entity_type="lemma",
        entity_id=lemma.id,
        details={
            "languages": missing_languages,
            "count": added_count,
            "task": "words.translations",
            "model": config.model,
            "via_worker": True,
        },
    )
    session.commit()
    return f"Added {added_count} translation(s) for {', '.join(missing_languages)}"


def do_regenerate_translations(session: Any, lemma_id: int, **_: Any) -> str:
    """Regenerate all non-Lithuanian translations for a lemma."""
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    config = _build_config()
    agent = VorasAgent(config=config)
    client = LinguisticClient(
        model=config.model or "",
        db_path=config.sqlite_path or "",
        debug=Config.DEBUG,
    )

    languages_to_regenerate = [
        language_code for language_code in LANGUAGE_FIELDS if language_code != "lt"
    ]
    for language_code in languages_to_regenerate:
        setattr(lemma, LANGUAGE_FIELDS[language_code][0], None)

    session.flush()

    reference_lang_code, reference_translation = get_reference_translation(
        session, lemma, exclude_languages=languages_to_regenerate
    )
    if not reference_translation:
        reference_lang_code = "en"
        reference_translation = lemma.lemma_text

    translations: Dict[str, Any] = {}
    for language_batch in split_llm_language_batches(languages_to_regenerate):
        batch_translations, success = client.query_translations(
            english_word=lemma.lemma_text,
            reference_translation=(
                reference_lang_code or "en",
                reference_translation or lemma.lemma_text,
            ),
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            languages=language_batch,
        )
        if not success or not batch_translations:
            raise RuntimeError(
                "LLM could not regenerate translations for " + ", ".join(language_batch)
            )
        translations.update(batch_translations)

    regenerated_count = 0
    for language_code in languages_to_regenerate:
        llm_field = lang_code_to_llm_field(language_code)
        if llm_field:
            translation_text = translations.get(llm_field, "").strip()
            if translation_text:
                agent.set_translation(session, lemma, language_code, translation_text)
                regenerated_count += 1

    log_operation(
        session,
        operation_type="translations_regenerated",
        entity_type="lemma",
        entity_id=lemma.id,
        details={
            "languages": languages_to_regenerate,
            "count": regenerated_count,
            "task": "words.translations.regenerate",
            "model": config.model,
            "via_worker": True,
        },
    )
    session.commit()
    return f"Regenerated {regenerated_count} translation(s)"


@workqueue_payload_handler()
def handle_words_translations(
    session: Any,
    lemma_id: Optional[int] = None,
    lemma_ids: Optional[List[int]] = None,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for missing translation generation."""
    if lemma_ids:
        results = [
            do_generate_missing_translations(
                session=session,
                lemma_id=queued_lemma_id,
                languages=languages,
                model=model,
            )
            for queued_lemma_id in lemma_ids
        ]
        return f"Batch completed for {len(lemma_ids)} lemmas: " + "; ".join(results)
    if lemma_id is None:
        raise ValueError("lemma_id or lemma_ids is required")
    return do_generate_missing_translations(
        session=session, lemma_id=lemma_id, languages=languages, model=model
    )


@workqueue_payload_handler()
def handle_words_translations_regenerate(session: Any, lemma_id: int, **_: Any) -> str:
    """Workqueue wrapper for translation regeneration.

    Accepts and ignores extra payload kwargs (``model``, etc.) added by the
    route so it is tolerant of payload changes.
    """
    return do_regenerate_translations(session=session, lemma_id=lemma_id)
