#!/usr/bin/python3

"""Shared translation logic for sentence translation.

This module provides reusable translation functionality that can be used by:
- ZVIRBLIS agent (batch translation)
- Barsukas web UI (single sentence translation)
- Future translation agents
"""

import json
import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from sentences.decomposition import (
    build_decomposition_schema,
    build_translate_and_decompose_prompt_from_english,
    query_sentence_decomposition,
)
from storage.models.schema import (
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
    SentencePatternWord,
)
from storage.translation_helpers import normalize_llm_language_codes

logger = logging.getLogger(__name__)


def _normalize_target_languages(target_languages: List[str]) -> List[str]:
    """Normalize and cap target languages for a single sentence-translation LLM call."""
    return normalize_llm_language_codes(
        target_languages,
        operation_name="Sentence translation",
    )


def build_translation_prompt(
    sentence: Sentence, target_languages: List[str], session: Session, include_english: bool = True
) -> Tuple[str, str]:
    """
    Build LLM prompt for translating a sentence.

    Args:
        sentence: Sentence object with English translation
        target_languages: List of language codes to translate to
        session: Database session for lemma lookups
        include_english: Whether to request English translation with word-by-word POS info

    Returns:
        Tuple of (context, prompt) strings
    """
    return build_translate_and_decompose_prompt_from_english(
        sentence,
        _normalize_target_languages(target_languages),
        session,
        include_english=include_english,
    )


def build_response_schema(
    target_languages: List[str], include_english: bool = True
) -> Dict[str, Any]:
    """
    Build JSON schema for LLM response.

    Args:
        target_languages: List of language codes to translate to
        include_english: Whether to include English translation and word breakdown in schema

    Returns:
        Schema dict suitable for clients.lib.schema_from_dict()
    """
    return build_decomposition_schema(
        target_languages=_normalize_target_languages(target_languages),
        include_english=include_english,
    )


def translate_sentence(
    sentence_id: int, target_languages: List[str], session: Session, model: str = "gpt-5-mini"
) -> Dict[str, Any]:
    """
    Translate a single sentence to target languages using LLM.

    Args:
        sentence_id: ID of sentence to translate
        target_languages: List of language codes (e.g., ["lt", "zh", "fr"])
        session: Database session
        model: LLM model to use

    Returns:
        Dict with translation results
    """
    # Get sentence and existing translations
    sentence = session.query(Sentence).get(sentence_id)
    if not sentence:
        raise ValueError(f"Sentence {sentence_id} not found")

    # Check if English word breakdown already exists
    # If not, include English in the translation request
    english_words = (
        session.query(SentenceWord).filter_by(sentence_id=sentence_id, language_code="en").all()
    )
    include_english = len(english_words) == 0

    normalized_target_languages = _normalize_target_languages(target_languages)

    # Build context, prompt and schema
    context, prompt = build_translation_prompt(
        sentence, normalized_target_languages, session, include_english
    )
    schema = build_response_schema(normalized_target_languages, include_english)

    client = UnifiedLLMClient()
    result = query_sentence_decomposition(
        prompt=prompt,
        client=client,
        model=model,
        json_schema=schema,
        context=context,
    )
    if not result.get("success"):
        raise ValueError(result.get("error", "No response data found in LLM result"))
    translations = {k: v for k, v in result.items() if k != "success"}

    # Store translations in database
    store_translation_results(sentence_id, translations, session)

    return translations


def store_translation_results(
    sentence_id: int, translations: Dict[str, Any], session: Session
) -> None:
    """
    Store translation results in database.

    Args:
        sentence_id: ID of sentence
        translations: Dict with translation data from LLM
        session: Database session
    """
    logger.info(f"=== Storing translations for sentence {sentence_id} ===")

    # Update English translation if provided
    if "en" in translations:
        logger.info(f"Updating English: {translations['en']}")
        en_trans = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code="en")
            .first()
        )
        if en_trans:
            en_trans.translation_text = translations["en"]

    # Store translations for each language
    for key, value in translations.items():
        if key == "en" or key.startswith("words_"):
            continue

        # This is a language translation
        lang_code = key
        translation_text = value

        logger.info(f"Storing translation for {lang_code}: {translation_text}")

        # Create or update translation
        existing = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code=lang_code)
            .first()
        )

        if existing:
            logger.debug(f"  -> Updating existing translation")
            existing.translation_text = translation_text
        else:
            logger.debug(f"  -> Creating new translation")
            new_translation = SentenceTranslation(
                sentence_id=sentence_id,
                language_code=lang_code,
                translation_text=translation_text,
                verified=False,
            )
            session.add(new_translation)

    # Store word-by-word data
    for key, words_data in translations.items():
        if not key.startswith("words_"):
            continue

        lang_code = key.replace("words_", "")
        logger.debug(f"Storing {len(words_data)} words for {lang_code}")

        # Delete existing word links for this language
        session.query(SentenceWord).filter_by(
            sentence_id=sentence_id, language_code=lang_code
        ).delete()

        # Add detailed word records
        for position, word_data in enumerate(words_data):
            # Find matching lemma by GUID if provided
            lemma_id = None
            guid = word_data.get("guid", "").strip()

            if guid:
                # Look up lemma by GUID
                lemma = session.query(Lemma).filter_by(guid=guid).first()
                if lemma:
                    lemma_id = lemma.id

            # Create SentenceWord with detailed grammatical info
            new_word = SentenceWord(
                sentence_id=sentence_id,
                lemma_id=lemma_id,
                language_code=lang_code,
                position=position,
                word_role=word_data.get("role"),
                english_text=word_data.get("english"),
                target_language_text=word_data.get("word"),
                grammatical_form=word_data.get("grammatical_form"),
                grammatical_case=None,
                declined_form=word_data.get("word"),
            )
            session.add(new_word)

    session.commit()
    logger.info(f"Stored translation results for sentence {sentence_id}")
