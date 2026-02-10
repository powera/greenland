#!/usr/bin/env python3
"""
Translation management for sentences.

This module handles the generation and storage of sentence translations
in multiple target languages using LLM-based translation, including
word-by-word breakdown with part-of-speech and lemma links.
"""

import json
import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from storage.database import Sentence
from storage.models.schema import SentenceWord
from storage.translation_helpers import (
    get_language_name,
    get_supported_languages,
)
from sentences.translation import (
    build_response_schema,
    build_translation_prompt,
    store_translation_results,
)

logger = logging.getLogger(__name__)


def ensure_translations(
    session: Session,
    sentence: Sentence,
    source_text: str,
    source_language: str,
    target_languages: List[str],
    model: str = "gpt-5-mini",
    verified: bool = False,
) -> Dict[str, Any]:
    """
    Ensure translations exist for a sentence in all target languages.

    This function generates translations with full word-by-word breakdown,
    including part-of-speech tagging and lemma links.

    Args:
        session: Database session
        sentence: Sentence object
        source_text: Source sentence text (unused, kept for API compatibility)
        source_language: Source language code
        target_languages: List of target language codes
        model: LLM model to use for translation
        verified: Whether translations are verified (unused, kept for API compatibility)

    Returns:
        Dictionary with translation results
    """
    logger.info(f"Ensuring translations for sentence {sentence.id} in: {target_languages}")

    # Check which translations already exist
    existing_translations = {t.language_code for t in sentence.translations}

    # Determine which translations need to be added
    needed_languages = [
        lang
        for lang in target_languages
        if lang not in existing_translations and lang != source_language
    ]

    if not needed_languages:
        logger.info("All translations already exist")
        return {"success": True, "added": 0, "skipped": len(target_languages)}

    # Check if English word breakdown already exists
    english_words = (
        session.query(SentenceWord).filter_by(sentence_id=sentence.id, language_code="en").all()
    )
    include_english = len(english_words) == 0

    try:
        # Build comprehensive prompt with word reference data
        context, prompt = build_translation_prompt(
            sentence, needed_languages, session, include_english
        )
    except ValueError as e:
        logger.error(f"Failed to build translation prompt: {e}")
        return {"success": False, "error": str(e)}

    # Build schema that includes word-by-word breakdown
    schema = build_response_schema(needed_languages, include_english)

    logger.info(f"Translating sentence {sentence.id} to {needed_languages}")

    try:
        # Call LLM with comprehensive schema
        client = UnifiedLLMClient()
        result = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            context=context,
            timeout=120,
        )

        # Parse response
        if result.structured_data:
            translations = result.structured_data
        elif result.response_text:
            translations = json.loads(result.response_text)
        else:
            logger.error("No response data from LLM")
            return {"success": False, "error": "LLM did not return data"}

        # Store translations AND word-by-word data
        store_translation_results(sentence.id, translations, session)

        # Count how many translations were added
        added_count = len(needed_languages)
        if include_english:
            added_count += 1  # English was also regenerated

        logger.info(f"Successfully translated sentence {sentence.id}")
        return {"success": True, "added": added_count, "skipped": len(existing_translations)}

    except Exception as e:
        logger.error(f"Error translating sentence {sentence.id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def validate_language_codes(codes: List[str]) -> List[str]:
    """
    Validate a list of language codes and return only the valid ones.

    Args:
        codes: List of language codes to validate

    Returns:
        List of valid language codes
    """
    supported = get_supported_languages()
    valid_codes = []
    for code in codes:
        if code in supported:
            valid_codes.append(code)
        else:
            logger.warning(f"Unsupported language code: {code}")
    return valid_codes
