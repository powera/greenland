#!/usr/bin/python3

"""Translation queries for linguistic analysis."""

import json
import logging
from typing import Dict, List, Optional, Tuple

from clients.types import Schema, SchemaProperty
import util.prompt_loader
from wordfreq.storage import database as linguistic_db
from wordfreq.translation.constants import DEFAULT_TRANSLATION_LANGUAGES

logger = logging.getLogger(__name__)


def query_translations(
    client,
    english_word: str,
    reference_translation: Tuple[str, str],
    definition: str,
    pos_type: str,
    get_session_func,
    pos_subtype: Optional[str] = None,
    languages: Optional[List[str]] = None,
    model: str = None,
) -> Tuple[Dict[str, str], bool]:
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
        languages: List of language names to translate to (e.g., ['french', 'spanish', 'german']).
                  If None, uses default set: ['chinese', 'korean', 'french', 'spanish', 'german', 'swahili', 'vietnamese']

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
        languages = [
            "chinese",
            "korean",
            "french",
            "spanish",
            "german",
            "portuguese",
            "swahili",
            "vietnamese",
        ]

    # Build schema properties dynamically based on requested languages
    schema_properties = {}
    languages_list_lines = []
    language_instructions_lines = []

    for lang in languages:
        if lang in DEFAULT_TRANSLATION_LANGUAGES:
            lang_config = DEFAULT_TRANSLATION_LANGUAGES[lang]
            schema_properties[lang_config["field"]] = SchemaProperty(
                "string", lang_config["description"]
            )
            # Add to languages list (e.g., "- French")
            languages_list_lines.append(f"- {lang.capitalize()}")
            # Add language instructions
            language_instructions_lines.append(lang_config["instructions"])
        else:
            logger.warning(f"Unknown language '{lang}' requested, skipping")

    if not schema_properties:
        logger.error("No valid languages specified")
        return {}, False

    schema = Schema(
        name="Translations",
        description="Translations for a word to multiple languages",
        properties=schema_properties,
    )

    context_template = util.prompt_loader.get_context("wordfreq", "translation_generation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "translation_generation")

    subtype_info = f"Subtype: {pos_subtype}" if pos_subtype else ""
    languages_list = "\n".join(languages_list_lines)
    language_instructions = "\n".join(language_instructions_lines)

    # Map language code to full language name
    lang_code_to_name_map = {
        "lt": "Lithuanian",
        "zh": "Chinese",
        "ko": "Korean",
        "fr": "French",
        "es": "Spanish",
        "de": "German",
        "pt": "Portuguese",
        "sw": "Swahili",
        "vi": "Vietnamese",
    }
    reference_language_name = lang_code_to_name_map.get(ref_lang_code, ref_lang_code.capitalize())

    # Format context with language instructions
    context = context_template.format(language_instructions=language_instructions)

    prompt = prompt_template.format(
        english_word=english_word,
        reference_language=reference_language_name,
        reference_translation=ref_translation,
        definition=definition,
        pos_type=pos_type,
        subtype_info=subtype_info,
        languages_list=languages_list,
    )

    try:
        response = client.generate_chat(
            prompt=prompt, model=model, json_schema=schema, context=context
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
                model=model,
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
        logger.error(f"Error generating translations for '{english_word}': {type(e).__name__}: {e}")
        return {}, False
