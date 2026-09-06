#!/usr/bin/python3

"""Translation queries for linguistic analysis."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage import database as linguistic_db
from storage.translation_helpers import (
    MAX_LLM_LANGUAGES_PER_OPERATION,
    LANGUAGE_NAMES,
    TRANSLATION_STATUS_VALUES,
)
from wordfreq.translation.constants import (
    AVAILABLE_TRANSLATION_LANGUAGES,
    AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE,
)

logger = logging.getLogger(__name__)


def query_translations(
    client: Any,
    english_word: str,
    reference_translation: Tuple[str, str],
    definition: str,
    pos_type: str,
    get_session_func: Callable,
    pos_subtype: Optional[str] = None,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Query LLM to generate translations for a word with known English, reference translation, and definition.

    This is used when you already have the English lemma, one reference translation, and definition
    in the database, and you just need to generate translations to other languages.

    Args:
        client: UnifiedLLMClient instance
        english_word: English lemma form
        reference_translation: Tuple of (language_code, translation) for a known translation in another language
                              e.g., ('lt', 'valgyti') or ('fr', 'manger'). Used as context for generating other translations.
        definition: Definition of the word
        pos_type: Part of speech (noun, verb, etc.)
        get_session_func: Function to get database session
        pos_subtype: Optional part of speech subtype
        languages: List of ISO language codes to translate to (e.g., ['fr', 'es', 'de']).
                  If None, uses default set: ['zh', 'ko', 'fr', 'es', 'de', 'pt', 'sw', 'vi']

    Returns:
        Tuple of (translations dict, success flag)
        translations dict has keys like: chinese_translation, french_translation, spanish_translation, etc.
    """
    if not english_word or not reference_translation or len(reference_translation) != 2:
        logger.error("English word and reference translation (lang_code, translation) are required")
        return {}, False

    ref_lang_code, ref_translation = reference_translation
    if not ref_lang_code or not ref_translation:
        logger.error("Reference translation must contain both language code and translation text")
        return {}, False

    # Use default languages if not specified
    if languages is None:
        languages = ["zh", "ko", "fr", "es", "de", "pt", "sw", "vi"]

    if len(languages) > MAX_LLM_LANGUAGES_PER_OPERATION:
        logger.warning(
            "Translation generation requested %s languages; limiting to first %s",
            len(languages),
            MAX_LLM_LANGUAGES_PER_OPERATION,
        )
        languages = languages[:MAX_LLM_LANGUAGES_PER_OPERATION]

    # Build schema properties dynamically based on requested languages
    schema_properties = {}
    languages_list_lines = []
    language_instructions_lines = []

    for lang_code in languages:
        lang_config = AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE.get(lang_code)
        if lang_config is None:
            logger.warning(f"Unknown language code '{lang_code}' requested, skipping")
            continue
        schema_properties[lang_config["field"]] = SchemaProperty(
            "object",
            lang_config["description"],
            properties={
                "translation": SchemaProperty("string", lang_config["description"]),
                "translation_status": SchemaProperty(
                    "string",
                    "How historically native the translation is: conventional, late_construction, modern_loan, descriptive, modern_reimagining, or uncertain. "
                    "'conventional' is the default and is discarded for modern languages, so it only ever matters that you mark the others.",
                    enum=sorted(TRANSLATION_STATUS_VALUES),
                ),
                "translation_status_note": SchemaProperty(
                    "string",
                    "Brief note when status is not conventional; otherwise an empty string.",
                ),
            },
        )
        # Use the canonical language name (without script qualifier) for the prompt bullet list
        display_name = LANGUAGE_NAMES.get(lang_code, lang_code)
        languages_list_lines.append(f"- {display_name}")
        language_instructions_lines.append(lang_config["instructions"])

    if not schema_properties:
        logger.error("No valid languages specified")
        return {}, False

    schema = Schema(
        name="Translations",
        description="Translations for a word to multiple languages",
        properties=schema_properties,
    )

    context_template = util.prompt_loader.get_context("translation", "word")
    prompt_template = util.prompt_loader.get_prompt("translation", "word")

    subtype_info = f"Subtype: {pos_subtype}" if pos_subtype else ""
    languages_list = "\n".join(languages_list_lines)
    language_instructions = "\n".join(language_instructions_lines)

    # Map language code to full language name (imported from translation_helpers)
    reference_language_name = LANGUAGE_NAMES.get(ref_lang_code, ref_lang_code.capitalize())

    # Format context with language instructions
    context = context_template.format(language_instructions=language_instructions)

    # Conditionally format reference info and disambiguation instruction
    # If reference language is English, we don't have a true reference translation
    if ref_lang_code != "en":
        reference_info = f'{reference_language_name}: "{ref_translation}" (lemma form)\n'
        disambiguation_instruction = f"Ensure all translations match the specific meaning indicated by the English and {reference_language_name} translations."
    else:
        # No reference translation - rely on definition and POS
        reference_info = ""
        disambiguation_instruction = "Ensure all translations match the specific meaning indicated by the definition and part of speech."

    prompt = prompt_template.format(
        english_word=english_word,
        reference_info=reference_info,
        definition=definition,
        pos_type=pos_type,
        subtype_info=subtype_info,
        languages_list=languages_list,
        disambiguation_instruction=disambiguation_instruction,
    )

    try:
        response = client.generate_chat(
            prompt=prompt, model=model, json_schema=schema, context=context
        )
        setattr(
            client, "_last_query_cost_usd", float(response.usage.cost) if response.usage else 0.0
        )

        # Log successful query
        session = get_session_func()
        try:
            linguistic_db.log_query(
                session,
                word=english_word,
                query_type="translation_generation",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=model or "unknown",
            )
        except Exception as log_err:
            logger.error(f"Failed to log successful query: {log_err}")

        # Validate and return response data
        if response.structured_data and isinstance(response.structured_data, dict):
            return response.structured_data, True
        else:
            logger.warning(f"Invalid response format for word '{english_word}'")
            return {}, False

    except Exception as e:
        setattr(client, "_last_query_cost_usd", 0.0)
        logger.error(f"Error generating translations for '{english_word}': {type(e).__name__}: {e}")
        return {}, False
