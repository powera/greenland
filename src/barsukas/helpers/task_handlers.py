"""Handlers that execute Barsukas background tasks.

This module imports workqueue handlers from src/workqueue/handlers/{agent}.py
and registers them in TASK_HANDLERS.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from config import Config

import constants
from agents.lape import LapeAgent
from agents.voras.agent import VorasAgent
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from wordfreq.storage.crud.operation_log import log_operation
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.translation_helpers import (
    LANG_CODE_TO_LLM_FIELD,
    LANGUAGE_FIELDS,
    get_reference_translation,
    get_translation,
    lang_code_to_llm_field,
)
from wordfreq.translation.client import LinguisticClient

# Import workqueue handlers from centralized workqueue package
from workqueue.handlers.lape import handle_generate_grammar_fact
from workqueue.handlers.papuga import handle_generate_pronunciations
from workqueue.handlers.sarka import handle_generate_conversation
from workqueue.handlers.sernas import handle_generate_synonyms
from workqueue.handlers.vieversys import handle_generate_audio, handle_generate_sentence_audio
from workqueue.handlers.vilkas import handle_generate_forms
from workqueue.handlers.voras import handle_add_missing_translations
from workqueue.handlers.zvirblis import handle_translate_sentence


def _build_config() -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )


def handle_voras_populate_translations(session: Any, payload: Dict) -> str:
    """Handle translation population task for voras agent."""
    lemma_id = payload.get("lemma_id")
    if not lemma_id:
        # Try target_id as fallback (standard barsukas field)
        lemma_id = payload.get("target_id")

    languages = payload.get("languages", [])

    if not lemma_id:
        raise ValueError("Missing lemma_id or target_id in payload")
    if not languages:
        raise ValueError("Missing languages in payload")

    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    # Create agent and client
    config = _build_config()
    agent = VorasAgent(config=config)
    client = LinguisticClient(
        model=config.model or "", db_path=config.sqlite_path or "", debug=Config.DEBUG
    )

    # Find which languages are missing for this lemma
    missing_languages = []
    for lang_code in languages:
        translation = get_translation(session, lemma, lang_code)
        if not translation or not translation.strip():
            missing_languages.append(lang_code)

    if not missing_languages:
        return "No missing translations to generate"

    # Get reference translation
    reference_lang_code, reference_translation = get_reference_translation(
        session, lemma, exclude_languages=missing_languages
    )

    if not reference_translation:
        # Use English as fallback
        reference_lang_code = "en"
        reference_translation = lemma.lemma_text

    # Build list of language names for LLM query
    from wordfreq.storage.translation_helpers import LANGUAGE_NAMES

    missing_lang_names = [LANGUAGE_NAMES.get(lc, lc).lower() for lc in missing_languages]

    # Query translations
    translations, success = client.query_translations(
        english_word=lemma.lemma_text,
        reference_translation=(
            reference_lang_code or "en",
            reference_translation or lemma.lemma_text,
        ),
        definition=lemma.definition_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        languages=missing_lang_names,
    )

    if not success or not translations:
        raise RuntimeError("LLM could not generate translations")

    # Map the LLM response fields to language codes and save translations
    added_count = 0
    for lang_code in missing_languages:
        llm_field = lang_code_to_llm_field(lang_code)
        if llm_field:
            translation = translations.get(llm_field, "").strip()
            if translation:
                agent.set_translation(session, lemma, lang_code, translation)
                added_count += 1

    log_operation(
        session,
        operation_type="translations_populated",
        entity_type="lemma",
        entity_id=lemma.id,
        details={
            "languages": missing_languages,
            "count": added_count,
            "agent": "voras",
            "model": config.model,
            "via_worker": True,
        },
    )

    session.commit()
    return f"Added {added_count} translation(s) for {', '.join(missing_languages)}"


def handle_voras_regenerate_translations(session: Any, payload: Dict) -> str:
    """Handle translation regeneration task for voras agent."""
    lemma_id = payload.get("lemma_id")
    if not lemma_id:
        # Try target_id as fallback (standard barsukas field)
        lemma_id = payload.get("target_id")

    if not lemma_id:
        raise ValueError("Missing lemma_id or target_id in payload")

    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    # Create agent and client
    config = _build_config()
    agent = VorasAgent(config=config)
    client = LinguisticClient(
        model=config.model or "", db_path=config.sqlite_path or "", debug=Config.DEBUG
    )

    # All languages except Lithuanian
    languages_to_regenerate = [lc for lc in LANGUAGE_FIELDS.keys() if lc != "lt"]

    # Delete existing non-Lithuanian translations
    for lang_code in languages_to_regenerate:
        field_name, _, _ = LANGUAGE_FIELDS[lang_code]
        existing = getattr(lemma, field_name, None)
        if existing and existing.strip():
            setattr(lemma, field_name, None)

    # Get Lithuanian translation as reference
    lt_translation = get_translation(session, lemma, "lt") or ""

    # Query translations for all languages
    translations, success = client.query_translations(
        english_word=lemma.lemma_text,
        reference_translation=("lt", lt_translation),
        definition=lemma.definition_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
    )

    if not success or not translations:
        raise RuntimeError("LLM could not generate translations")

    # Add all non-Lithuanian translations
    added_count = 0
    for lang_code in languages_to_regenerate:
        field_name, _, _ = LANGUAGE_FIELDS[lang_code]
        llm_field = LANG_CODE_TO_LLM_FIELD.get(lang_code)
        translation = translations.get(llm_field or "", "").strip()

        if translation:
            setattr(lemma, field_name, translation)
            added_count += 1

    log_operation(
        session,
        operation_type="translations_regenerated",
        entity_type="lemma",
        entity_id=lemma.id,
        details={
            "languages": languages_to_regenerate,
            "count": added_count,
            "agent": "voras",
            "model": config.model,
            "via_worker": True,
        },
    )

    session.commit()
    return f"Regenerated {added_count} translation(s) for {lemma.lemma_text}"


def handle_lape_generate_grammar_fact(session: Any, payload: Dict) -> str:
    """Handle grammar fact generation task for lape agent."""
    lemma_id = payload.get("lemma_id")
    if not lemma_id:
        # Try target_id as fallback (standard barsukas field)
        lemma_id = payload.get("target_id")

    fact_type = payload.get("fact_type")
    language_code = payload.get("language_code")

    if not lemma_id:
        raise ValueError("Missing lemma_id or target_id in payload")
    if not fact_type:
        raise ValueError("Missing fact_type in payload")
    if not language_code:
        raise ValueError("Missing language_code in payload")

    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    # Check if fact already exists
    existing_fact = get_grammar_fact_value(session, lemma.id, language_code, fact_type)
    if existing_fact is not None:
        return f"Fact already exists: {fact_type}={existing_fact}"

    # Create agent
    config = _build_config()
    agent = LapeAgent(config=config)

    # Get translation if needed for this fact type
    translation = None
    if fact_type not in ["verb_transitivity", "countability", "animacy"]:
        translation = get_translation(session, lemma, language_code)
        if not translation:
            raise ValueError(f"No {language_code} translation found for lemma {lemma.lemma_text}")

    # Generate the fact
    fact_value, notes, confidence = agent.generate_fact(
        fact_type=fact_type,
        lemma=lemma,
        language_code=language_code,
        translation=translation,
        session=session,
    )

    # Check confidence threshold
    min_confidence = 0.7
    if not fact_value or confidence < min_confidence:
        raise RuntimeError(
            f"Low confidence or no value: {fact_value} (confidence: {confidence:.2f})"
        )

    # Save the fact
    add_grammar_fact(
        session,
        lemma_id=lemma.id,
        language_code=language_code,
        fact_type=fact_type,
        fact_value=fact_value,
        notes=notes,
        verified=False,
    )

    # Log the operation
    log_operation(
        session,
        operation_type="grammar_fact_generated",
        entity_type="grammar_fact",
        entity_id=lemma.id,
        details={
            "fact_type": fact_type,
            "language_code": language_code,
            "fact_value": fact_value,
            "confidence": confidence,
            "agent": "lape",
            "model": config.model,
            "via_worker": True,
        },
    )

    session.commit()
    return f"Generated {fact_type}={fact_value} (confidence: {confidence:.2f})"


TASK_HANDLERS = {
    "add_missing_translations": handle_add_missing_translations,
    "generate_pronunciations": handle_generate_pronunciations,
    "generate_forms": handle_generate_forms,
    "generate_synonyms": handle_generate_synonyms,
    "translate_sentence": handle_translate_sentence,
    "generate_audio": handle_generate_audio,
    "generate_sentence_audio": handle_generate_sentence_audio,
    "generate_grammar_fact": handle_generate_grammar_fact,
    "lape_generate_grammar_fact": handle_lape_generate_grammar_fact,
    "sarka_generate_conversation": handle_generate_conversation,
    "voras_populate_translations": handle_voras_populate_translations,
    "voras_regenerate_translations": handle_voras_regenerate_translations,
}
