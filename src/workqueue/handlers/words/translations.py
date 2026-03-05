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
    LANGUAGE_NAMES,
    get_reference_translation,
    get_translation,
    lang_code_to_llm_field,
)
from wordfreq.translation.client import LinguisticClient
from workqueue.tools import workqueue_payload_handler


def _build_config() -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )


def do_generate_missing_translations(
    session: Any,
    lemma_id: int,
    languages: Optional[List[str]] = None,
    **_: Any,
) -> str:
    """Generate missing translations for a lemma, optionally constrained to languages."""
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    requested_languages = languages or list(LANGUAGE_FIELDS.keys())
    missing_languages: List[str] = []
    for language_code in requested_languages:
        if language_code == "lt":
            continue
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

    missing_language_names = [LANGUAGE_NAMES.get(code, code).lower() for code in missing_languages]

    config = _build_config()
    agent = VorasAgent(config=config)
    client = LinguisticClient(
        model=config.model or "",
        db_path=config.sqlite_path or "",
        debug=Config.DEBUG,
    )
    translations, success = client.query_translations(
        english_word=lemma.lemma_text,
        reference_translation=(
            reference_lang_code or "en",
            reference_translation or lemma.lemma_text,
        ),
        definition=lemma.definition_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        languages=missing_language_names,
    )

    if not success or not translations:
        raise RuntimeError("LLM could not generate translations")

    added_count = 0
    for language_code in missing_languages:
        llm_field = lang_code_to_llm_field(language_code)
        if llm_field:
            translation_text = translations.get(llm_field, "").strip()
            if translation_text:
                agent.set_translation(session, lemma, language_code, translation_text)
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

    missing_language_names = [
        LANGUAGE_NAMES.get(code, code).lower() for code in languages_to_regenerate
    ]
    translations, success = client.query_translations(
        english_word=lemma.lemma_text,
        reference_translation=(
            reference_lang_code or "en",
            reference_translation or lemma.lemma_text,
        ),
        definition=lemma.definition_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        languages=missing_language_names,
    )

    if not success or not translations:
        raise RuntimeError("LLM could not regenerate translations")

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
    session: Any, lemma_id: int, languages: Optional[List[str]] = None
) -> str:
    """Workqueue wrapper for missing translation generation."""
    return do_generate_missing_translations(session=session, lemma_id=lemma_id, languages=languages)


@workqueue_payload_handler()
def handle_words_translations_regenerate(session: Any, lemma_id: int) -> str:
    """Workqueue wrapper for translation regeneration."""
    return do_regenerate_translations(session=session, lemma_id=lemma_id)
