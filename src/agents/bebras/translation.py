#!/usr/bin/env python3
"""
Translation management for sentences.

This module handles the generation and storage of sentence translations
in multiple target languages using LLM-based translation.
"""

import logging
from typing import List, Dict, Optional

import util.prompt_loader
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty
from wordfreq.storage.database import (
    Sentence,
    add_sentence_translation
)

logger = logging.getLogger(__name__)


# Language name mappings for prompts
LANGUAGE_NAMES = {
    "en": "English",
    "lt": "Lithuanian",
    "zh": "Chinese",
    "fr": "French",
    "ko": "Korean",
    "sw": "Swahili",
    "vi": "Vietnamese",
    "de": "German",
    "es": "Spanish",
    "ja": "Japanese"
}


def ensure_translations(
    session,
    sentence: Sentence,
    source_text: str,
    source_language: str,
    target_languages: List[str],
    model: str = "gpt-5-mini",
    verified: bool = False
) -> Dict[str, any]:
    """
    Ensure translations exist for a sentence in all target languages.

    Args:
        session: Database session
        sentence: Sentence object
        source_text: Source sentence text
        source_language: Source language code
        target_languages: List of target language codes
        model: LLM model to use for translation
        verified: Whether translations are verified

    Returns:
        Dictionary with translation results
    """
    logger.info(f"Ensuring translations for sentence {sentence.id} in: {target_languages}")

    # Check which translations already exist
    existing_translations = {
        t.language_code for t in sentence.translations
    }

    # Determine which translations need to be added
    needed_languages = [
        lang for lang in target_languages
        if lang not in existing_translations and lang != source_language
    ]

    if not needed_languages:
        logger.info("All translations already exist")
        return {
            "success": True,
            "added": 0,
            "skipped": len(target_languages)
        }

    # Generate translations via LLM
    translations = translate_sentence(
        source_text=source_text,
        source_language=source_language,
        target_languages=needed_languages,
        model=model
    )

    if not translations.get("success"):
        return translations

    # Add translations to database
    added_count = 0
    for lang_code, translation_text in translations.get("translations", {}).items():
        try:
            add_sentence_translation(
                session=session,
                sentence=sentence,
                language_code=lang_code,
                translation_text=translation_text,
                verified=verified
            )
            added_count += 1
            logger.info(f"Added {lang_code} translation: {translation_text}")
        except Exception as e:
            logger.error(f"Failed to add {lang_code} translation: {e}")

    return {
        "success": True,
        "added": added_count,
        "skipped": len(existing_translations)
    }


def translate_sentence(
    source_text: str,
    source_language: str,
    target_languages: List[str],
    model: str = "gpt-5-mini"
) -> Dict[str, any]:
    """
    Translate a sentence to multiple target languages using LLM.

    Args:
        source_text: Source sentence text
        source_language: Source language code
        target_languages: List of target language codes
        model: LLM model to use

    Returns:
        Dictionary with translation results
    """
    logger.info(f"Translating '{source_text}' to {target_languages}")

    source_lang_name = LANGUAGE_NAMES.get(source_language, source_language)
    target_lang_names = [
        LANGUAGE_NAMES.get(lang, lang) for lang in target_languages
    ]

    # Load prompt templates
    prompt_context = util.prompt_loader.get_context("wordfreq", "sentence_translation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "sentence_translation")

    # Format the prompt with parameters
    formatted_prompt = prompt_template.format(
        source_lang_name=source_lang_name,
        target_lang_names=", ".join(target_lang_names),
        source_text=source_text,
        target_lang_codes=", ".join(target_languages)
    )

    # Combine context and prompt
    prompt = f"{prompt_context}\n\n{formatted_prompt}"

    # Build schema with properties for each target language
    properties = {}
    for lang_code in target_languages:
        lang_name = LANGUAGE_NAMES.get(lang_code, lang_code)
        properties[lang_code] = SchemaProperty(
            type="string",
            description=f"Translation in {lang_name}"
        )

    schema = Schema(
        name="Translations",
        description="Sentence translations in multiple languages",
        properties=properties
    )

    try:
        llm_client = UnifiedLLMClient()
        response = llm_client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            timeout=60
        )

        if response.structured_data:
            translations = response.structured_data
            logger.info(f"Generated {len(translations)} translations")
            return {
                "success": True,
                "translations": translations
            }
        else:
            logger.error("No structured data received from LLM")
            return {
                "success": False,
                "error": "LLM did not return structured data"
            }

    except Exception as e:
        logger.error(f"Error translating sentence: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def get_language_name(language_code: str) -> str:
    """
    Get the full name for a language code.

    Args:
        language_code: ISO 639-1 language code

    Returns:
        Language name
    """
    return LANGUAGE_NAMES.get(language_code, language_code.upper())


def validate_language_codes(language_codes: List[str]) -> List[str]:
    """
    Validate and normalize language codes.

    Args:
        language_codes: List of language codes to validate

    Returns:
        List of valid, normalized language codes
    """
    valid_codes = []
    for code in language_codes:
        normalized = code.lower().strip()
        if len(normalized) == 2:  # ISO 639-1 codes are 2 letters
            valid_codes.append(normalized)
        else:
            logger.warning(f"Invalid language code: {code}")

    return valid_codes
