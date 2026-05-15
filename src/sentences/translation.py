#!/usr/bin/python3

"""Shared translation logic for sentence translation.

This module provides reusable translation functionality that can be used by:
- ZVIRBLIS agent (batch translation)
- Barsukas web UI (single sentence translation)
- Future translation agents
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from sentences.decomposition import (
    build_decomposition_schema,
    build_prompt_for_translate_and_decompose,
)
from storage.models.schema import (
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
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
    sentence: Sentence,
    target_languages: List[str],
    session: Session,
    include_english: bool = True,
    *,
    source_language: str = "en",
    candidate_lemmas: Optional[List[Lemma]] = None,
) -> Tuple[str, str]:
    """
    Build LLM prompt for translating a sentence.

    Args:
        sentence: Sentence object with a translation in ``source_language``
        target_languages: List of language codes to translate to
        session: Database session for lemma lookups
        include_english: Whether to request English translation with word-by-word POS info
        source_language: Language code of the existing SentenceTranslation to use
            as the prompt's template sentence (default: "en").
        candidate_lemmas: Optional ranked list of Lemmas the LLM should prefer.

    Returns:
        Tuple of (context, prompt) strings
    """
    return build_prompt_for_translate_and_decompose(
        sentence,
        _normalize_target_languages(target_languages),
        session,
        include_english=include_english,
        source_language=source_language,
        candidate_lemmas=candidate_lemmas,
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
    sentence_id: int,
    target_languages: List[str],
    session: Session,
    model: str = "gpt-5.4-mini",
    *,
    source_language: str = "en",
) -> Dict[str, Any]:
    """Translate a stored sentence into target languages using the 3-phase pipeline.

    Phase 1 produces per-language translations, Phase 2 ranks DB candidate lemmas
    for the English version, and Phase 3 decomposes EACH target language plus
    English (when missing) into word-level entries. Per-language Phase 3 calls
    cost more LLM tokens than the old single-call shape, but produce
    higher-quality ``SentenceWord`` rows for morphologically rich languages.

    Args:
        sentence_id: ID of sentence to translate.
        target_languages: List of language codes (e.g., ["lt", "zh", "fr"]).
        session: Database session.
        model: LLM model to use.
        source_language: Language code of the existing SentenceTranslation to use
            as the prompt's source sentence (default: "en").

    Returns:
        Dict of language_code -> translation_text for the languages that were
        produced this call (includes English when it was missing). Per-language
        word breakdowns are persisted to ``SentenceWord`` as a side effect.
    """
    from sentences.translate_and_decompose import translate_and_decompose

    sentence = session.query(Sentence).get(sentence_id)
    if not sentence:
        raise ValueError(f"Sentence {sentence_id} not found")

    source_translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code=source_language)
        .first()
    )
    if not source_translation:
        raise ValueError(
            f"Sentence {sentence_id} has no translation in source language '{source_language}'"
        )

    english_words = (
        session.query(SentenceWord).filter_by(sentence_id=sentence_id, language_code="en").all()
    )
    include_english = len(english_words) == 0

    normalized_targets_all = _normalize_target_languages(target_languages)
    # Phase 1 must not retranslate the source language back to itself.
    phase1_targets = [lang for lang in normalized_targets_all if lang != source_language]

    # Phase 3 should decompose every language the caller asked for, including
    # the source language: callers requesting "decompose lt" for an LT-source
    # sentence still want LT SentenceWord rows produced from the existing
    # source translation. translate_and_decompose handles a decompose_languages
    # entry that has no Phase 1 translation by falling back to the source text.
    decompose_languages: List[str] = list(normalized_targets_all)
    if include_english and "en" not in decompose_languages and source_language != "en":
        decompose_languages.append("en")

    client = UnifiedLLMClient()
    pipeline_result = translate_and_decompose(
        sentence_text=source_translation.translation_text,
        source_language=source_language,
        session=session,
        client=client,
        target_languages=phase1_targets,
        decompose_languages=decompose_languages,
        model=model,
    )

    if not pipeline_result.phase1_ok:
        raise ValueError(pipeline_result.phase1_error or "Phase 1 translation failed")

    translations: Dict[str, Any] = dict(pipeline_result.translations)

    # Adapt Phase 3 output to the legacy "translations" dict shape consumed by
    # store_translation_results: keys "lang" / "words_lang".
    for language_code, decomposition in pipeline_result.decompositions.items():
        if not decomposition.success:
            logger.warning(
                "Phase 3 decomposition failed for sentence %d, language %s: %s",
                sentence_id,
                language_code,
                decomposition.error,
            )
            continue
        if language_code not in translations and decomposition.translation:
            translations[language_code] = decomposition.translation
        translations[f"words_{language_code}"] = [
            _adapt_decomposed_word(word_entry) for word_entry in decomposition.words
        ]

    store_translation_results(sentence_id, translations, session)
    return translations


def _adapt_decomposed_word(word_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Phase 3 ``words[]`` entry to the legacy ``words_<lang>`` shape.

    Phase 3 uses ``surface_form`` / ``english_gloss`` / ``lemma_guid``; the
    legacy storage path expects ``word`` / ``english`` / ``guid``.
    """
    grammatical_form_raw = word_entry.get("grammatical_form")
    grammatical_form: Optional[str]
    if grammatical_form_raw is None:
        grammatical_form = None
    else:
        stripped = str(grammatical_form_raw).strip()
        grammatical_form = stripped or None
    return {
        "word": str(word_entry.get("surface_form") or "").strip(),
        "english": str(word_entry.get("english_gloss") or "").strip(),
        "guid": str(word_entry.get("lemma_guid") or "").strip(),
        "role": str(word_entry.get("role") or "").strip(),
        "grammatical_form": grammatical_form,
    }


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

    # Update or create English translation if provided
    if "en" in translations:
        logger.info(f"Updating English: {translations['en']}")
        en_trans = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code="en")
            .first()
        )
        if en_trans:
            en_trans.translation_text = translations["en"]
        else:
            session.add(
                SentenceTranslation(
                    sentence_id=sentence_id,
                    language_code="en",
                    translation_text=translations["en"],
                    verified=False,
                )
            )

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
            is_synthetic_guid = guid.startswith("SYN") and guid[3:].isdigit()

            if guid and not is_synthetic_guid:
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
