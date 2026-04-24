#!/usr/bin/env python3
"""
Translation management for sentences.

This module handles the generation and storage of sentence translations
in multiple target languages using LLM-based translation, including
word-by-word breakdown with part-of-speech and lemma links.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from sentences.candidate_lookup import find_candidate_lemmas_by_english_word
from storage.database import Sentence
from storage.models.schema import Lemma, SentencePatternWord, SentenceWord
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
    model: str = "gpt-5.4-mini",
    verified: bool = False,
    *,
    pivot_languages: Optional[Sequence[str]] = None,
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
        pivot_languages: When provided and the sentence has no SentencePatternWord
            lemma rows, disambiguate candidate lemmas using these pivot-language
            translations (must already be present as SentenceTranslation rows).

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

    candidate_lemmas: Optional[List[Lemma]] = None
    if pivot_languages:
        has_pattern_lemmas = (
            session.query(SentencePatternWord.id)
            .filter(
                SentencePatternWord.sentence_id == sentence.id,
                SentencePatternWord.lemma_id.isnot(None),
            )
            .first()
            is not None
        )
        if not has_pattern_lemmas:
            grouped = find_candidate_lemmas_by_english_word(
                session,
                sentence.id,
                pivot_languages=pivot_languages,
                target_languages=needed_languages,
            )
            seen_lemma_ids: set[int] = set()
            flattened: List[Lemma] = []
            for english_word, candidates in grouped.items():
                for candidate in candidates:
                    lemma = session.query(Lemma).filter_by(guid=candidate.guid).first()
                    if lemma is None or lemma.id in seen_lemma_ids:
                        continue
                    seen_lemma_ids.add(lemma.id)
                    flattened.append(lemma)
            if flattened:
                candidate_lemmas = flattened
                logger.info(
                    "Pattern-less sentence %s: supplying %d candidate lemmas from pivot lookup",
                    sentence.id,
                    len(flattened),
                )

    try:
        # Build comprehensive prompt with word reference data
        context, prompt = build_translation_prompt(
            sentence,
            needed_languages,
            session,
            include_english,
            candidate_lemmas=candidate_lemmas,
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
