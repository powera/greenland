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
from sentences.candidate_lookup import find_candidate_lemmas_for_sentence
from storage.database import Sentence
from storage.models.schema import (
    Lemma,
    SentenceTranslation,
    SentenceWord,
    SentenceWordHint,
)
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


def find_sentences_needing_translations(
    session: Session,
    *,
    lemma_id: int,
    target_languages: Sequence[str],
    limit: Optional[int] = None,
    require_english_source: bool = False,
) -> List[int]:
    """Return linked sentence IDs that still need one of the target languages.

    ``limit`` is the desired number of fully translated sentences for the
    lemma, so already-complete sentences count toward it.
    """
    sentence_word_ids = (
        session.query(SentenceWord.sentence_id).filter(SentenceWord.lemma_id == lemma_id).distinct()
    )
    word_hint_ids = (
        session.query(SentenceWordHint.sentence_id)
        .filter(SentenceWordHint.lemma_id == lemma_id)
        .distinct()
    )
    sentence_ids = [
        sentence_id
        for (sentence_id,) in session.query(Sentence.id)
        .filter((Sentence.id.in_(sentence_word_ids)) | (Sentence.id.in_(word_hint_ids)))
        .order_by(Sentence.id)
        .all()
    ]

    required_languages = {*target_languages, "en"}
    incomplete_ids: List[int] = []
    complete_count = 0
    for sentence_id in sentence_ids:
        existing_languages = {
            language_code
            for (language_code,) in session.query(SentenceTranslation.language_code)
            .filter(SentenceTranslation.sentence_id == sentence_id)
            .all()
        }
        if required_languages.issubset(existing_languages):
            complete_count += 1
        elif not require_english_source or "en" in existing_languages:
            incomplete_ids.append(sentence_id)

    if limit is None:
        return incomplete_ids
    remaining_count = max(0, limit - complete_count)
    return incomplete_ids[:remaining_count]


def translate_sentence_simple(
    session: Session,
    *,
    sentence_id: int,
    target_languages: Sequence[str],
) -> int:
    """Add missing text-only translations with TranslateGemma."""
    from clients.translategemma_client import TranslateGemmaClient

    source_text = (
        session.query(SentenceTranslation.translation_text)
        .filter(
            SentenceTranslation.sentence_id == sentence_id,
            SentenceTranslation.language_code == "en",
        )
        .scalar()
    )
    if not source_text:
        raise ValueError(f"Sentence {sentence_id} has no English translation")

    existing_languages = {
        language_code
        for (language_code,) in session.query(SentenceTranslation.language_code)
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .all()
    }
    client = TranslateGemmaClient()
    added_count = 0
    for language_code in target_languages:
        if language_code == "en" or language_code in existing_languages:
            continue
        response = client.generate_translation(
            text=source_text,
            source_lang="en",
            target_lang=language_code,
        )
        if not response.response_text:
            raise RuntimeError(
                f"TranslateGemma returned no {language_code} translation for sentence {sentence_id}"
            )
        session.add(
            SentenceTranslation(
                sentence_id=sentence_id,
                language_code=language_code,
                translation_text=response.response_text,
                verified=False,
            )
        )
        added_count += 1
    session.flush()
    return added_count


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
        pivot_languages: When provided and the sentence has no SentenceWordHint
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
            session.query(SentenceWordHint.id)
            .filter(
                SentenceWordHint.sentence_id == sentence.id,
                SentenceWordHint.lemma_id.isnot(None),
            )
            .first()
            is not None
        )
        if not has_pattern_lemmas:
            source_pool: List[str] = list(
                dict.fromkeys([*pivot_languages, *needed_languages, "en"])
            )
            ranked = find_candidate_lemmas_for_sentence(
                session,
                sentence.id,
                source_languages=source_pool,
            )
            seen_lemma_ids: set[int] = set()
            flattened: List[Lemma] = []
            for candidate in ranked:
                lemma = session.query(Lemma).filter_by(guid=candidate.guid).first()
                if lemma is None or lemma.id in seen_lemma_ids:
                    continue
                seen_lemma_ids.add(lemma.id)
                flattened.append(lemma)
            if flattened:
                candidate_lemmas = flattened
                logger.info(
                    "Pattern-less sentence %s: supplying %d candidate lemmas from multi-language lookup",
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
