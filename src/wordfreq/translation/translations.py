#!/usr/bin/python3

"""Translation queries for linguistic analysis."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.translation_helpers import LANGUAGE_NAMES
from wordfreq.translation.constants import DEFAULT_TRANSLATION_LANGUAGES, REGIONAL_VARIANT_LANGUAGES

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
                  If None, uses default set: ['chinese', 'korean', 'french', 'spanish', 'german', 'portuguese', 'swahili', 'vietnamese']

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
        logger.error(f"Error generating translations for '{english_word}': {type(e).__name__}: {e}")
        return {}, False


def query_regional_variants(
    client: Any,
    english_word: str,
    base_translation: str,
    base_language_code: str,
    definition: str,
    pos_type: str,
    get_session_func: Callable,
    model: Optional[str] = None,
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM to generate regional variants for a pluricentric language translation.

    This is called AFTER the base translation exists. It asks the LLM to provide
    regional variants where they differ from the base translation.

    Args:
        client: UnifiedLLMClient instance
        english_word: English lemma form
        base_translation: Existing translation in base form (e.g., "color" for en, "ordenador" for es)
        base_language_code: Language code (e.g., 'en', 'es', 'pt', 'zh')
        definition: Definition of the word
        pos_type: Part of speech (noun, verb, etc.)
        get_session_func: Function to get database session
        model: Optional model override

    Returns:
        Tuple of (regional_variants dict, success flag)
        regional_variants dict has keys like: en-US, en-GB, en-AU (only if different from base)
        Returns empty dict if no variants differ from base.
    """
    if base_language_code not in REGIONAL_VARIANT_LANGUAGES:
        logger.debug(
            f"Language '{base_language_code}' is not pluricentric, skipping regional variants"
        )
        return {}, True  # Success but no variants needed

    lang_config = REGIONAL_VARIANT_LANGUAGES[base_language_code]
    variants = cast(Dict[str, Dict[str, str]], lang_config["variants"])

    # Build schema properties for each regional variant
    schema_properties = {}
    for region_code, region_info in variants.items():
        schema_properties[region_code] = SchemaProperty(
            "string",
            f"{region_info['name']}: translation if different from base, or 'SAME' if identical",
        )

    schema = Schema(
        name="RegionalVariants",
        description=f"Regional variants for {lang_config['display_name']} translation",
        properties=schema_properties,
    )

    # Build variant descriptions for prompt
    variant_descriptions = []
    for region_code, region_info in variants.items():
        variant_descriptions.append(
            f"- {region_code} ({region_info['name']}): {region_info['description']}"
        )

    prompt = f"""Given the following word and its base {lang_config['display_name']} translation, provide regional variants where they differ.

English word: "{english_word}"
Definition: {definition}
Part of speech: {pos_type}
Base translation: "{base_translation}"

Regional variants to check:
{chr(10).join(variant_descriptions)}

For each region, provide:
- The regional translation if it differs from the base translation
- The string "SAME" if the translation is identical to the base

Only provide different translations where there are genuine regional vocabulary or spelling differences.
Provide translations in lemma form (infinitive for verbs, singular for nouns)."""

    context = f"""You are a linguistic expert specializing in regional variations of {lang_config['display_name']}.
Your task is to identify when regional variants differ from a base translation.

Guidelines:
- Only mark as different when there's a genuine regional difference in vocabulary or spelling
- Spelling differences count (e.g., color/colour, organize/organise)
- Vocabulary differences count (e.g., truck/lorry, elevator/lift)
- Minor pronunciation-only differences should be marked as "SAME"
- When in doubt, mark as "SAME" - we only want genuine lexical differences"""

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
                query_type="regional_variant_generation",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=model or "unknown",
            )
        except Exception as log_err:
            logger.error(f"Failed to log regional variant query: {log_err}")

        # Process response - filter out "SAME" values
        if response.structured_data and isinstance(response.structured_data, dict):
            result = {}
            for region_code, translation in response.structured_data.items():
                if (
                    translation
                    and translation.upper() != "SAME"
                    and translation != base_translation
                ):
                    result[region_code] = translation
            return result, True
        else:
            logger.warning(f"Invalid response format for regional variants of '{english_word}'")
            return {}, False

    except Exception as e:
        logger.error(
            f"Error generating regional variants for '{english_word}': {type(e).__name__}: {e}"
        )
        return {}, False
