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
    build_name_rendering_lines,
    build_prompt_for_translate_and_decompose,
)
from storage.crud.operation_log import (
    SENTENCE_TRANSLATION_UPDATE,
    SENTENCE_WORD_CREATE,
    log_batch_operation,
    log_entity_operation,
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
    log_source: Optional[str] = None,
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
        log_source: Who is running this, for the operation log. None skips
            logging. Named to keep it distinct from ``source_language``.

    Returns:
        Dict of language_code -> translation_text for the languages that were
        produced this call (includes English when it was missing). Per-language
        word breakdowns are persisted to ``SentenceWord`` as a side effect.
    """
    from sentences.candidate_lookup import DEFAULT_SOURCE_LANGUAGES
    from sentences.translate_and_decompose import (
        TranslateAndDecomposeResult,
        decompose_with_existing_translations,
        format_conversation_context,
        translate_sentence_text,
    )
    from storage.crud.conversation import get_sentence_conversation_context

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

    # Add candidate-lookup pivots to Phase 1 so Phase 2 has enough languages to
    # rank lemmas against (PHASE3_MIN_LANGUAGES precondition in
    # translate_and_decompose).
    phase1_languages: List[str] = list(phase1_targets)
    seen_phase1: set[str] = {source_language, *phase1_languages}
    for pivot in DEFAULT_SOURCE_LANGUAGES:
        if pivot not in seen_phase1:
            phase1_languages.append(pivot)
            seen_phase1.add(pivot)

    # Phase 3 should decompose every language the caller asked for, including
    # the source language: callers requesting "decompose lt" for an LT-source
    # sentence still want LT SentenceWord rows produced from the existing
    # source translation. decompose_with_existing_translations handles a
    # decompose_languages entry that has no Phase 1 translation by falling back
    # to the source text.
    #
    # The same applies to English: it is decomposed whenever it has no
    # SentenceWord rows yet, including when it IS the source language. Gating
    # this on source_language != "en" (as an earlier version did) mirrored the
    # Phase-1 "don't retranslate the source" rule into a phase where it does
    # not apply, and left every English-source sentence without English words.
    decompose_languages: List[str] = list(normalized_targets_all)
    if include_english and "en" not in decompose_languages:
        decompose_languages.append("en")

    client = UnifiedLLMClient()
    source_text = source_translation.translation_text

    # A dialog line translated in isolation loses what it is answering, which
    # is what turns an elliptical reply into a stranded copula in every
    # language. Standalone sentences get None here and the ordinary prompt.
    conversation_context_obj = get_sentence_conversation_context(
        session, sentence_id, language_code=source_language
    )
    conversation_context = (
        format_conversation_context(conversation_context_obj) or None
        if conversation_context_obj is not None
        else None
    )

    # Pin the established spelling of any names this sentence casts, so the
    # same character is not spelled differently in consecutive sentences.
    name_rendering_lines = build_name_rendering_lines(sentence, phase1_languages, session)

    # ── Phase 1: translate, then PERSIST before Phase 3 ────────────────────
    phase1_translations = translate_sentence_text(
        sentence_text=source_text,
        source_language=source_language,
        target_languages=phase1_languages,
        client=client,
        model=model,
        conversation_context=conversation_context,
        name_renderings="\n".join(name_rendering_lines) or None,
    )
    if not phase1_translations:
        raise ValueError("Phase 1 translation produced no results")

    # Persist Phase 1 translations (SentenceTranslation rows only) and commit
    # before Phase 3. This way the explicit batch decompose path's precondition
    # is satisfied on retry, and a Phase-3 failure doesn't lose the Phase-1
    # work.
    _persist_phase1_translations(sentence_id, phase1_translations, session, source=log_source)

    # ── Phase 2 + Phase 3 ─────────────────────────────────────────────────
    pipeline_result = TranslateAndDecomposeResult(
        source_sentence=source_text,
        source_language=source_language,
    )
    pipeline_result.translations = dict(phase1_translations)

    decompose_with_existing_translations(
        sentence_text=source_text,
        source_language=source_language,
        translations=phase1_translations,
        session=session,
        client=client,
        decompose_languages=decompose_languages,
        model=model,
        result=pipeline_result,
    )

    translations: Dict[str, Any] = dict(pipeline_result.translations)

    # Flatten Phase 3 output into the "translations" dict shape consumed by
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
        translations[f"words_{language_code}"] = list(decomposition.words)

    store_translation_results(sentence_id, translations, session, source=log_source)
    return translations


def _persist_phase1_translations(
    sentence_id: int,
    translations: Dict[str, str],
    session: Session,
    source: Optional[str] = None,
) -> None:
    """Insert/update SentenceTranslation rows for Phase-1 outputs and commit.

    Used by the synchronous decompose path so Phase-1 work survives a Phase-3
    failure and so the DB state matches what the explicit two-phase OpenAI
    Batch flow produces.

    Args:
        sentence_id: Sentence being translated.
        translations: Phase-1 output, language code -> text.
        session: Database session.
        source: Who produced these, for the operation log. None skips logging.
    """
    persisted: List[str] = []
    for lang_code, translation_text in translations.items():
        if not isinstance(translation_text, str) or not translation_text.strip():
            continue
        existing = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code=lang_code)
            .first()
        )
        if existing:
            existing.translation_text = translation_text
        else:
            session.add(
                SentenceTranslation(
                    sentence_id=sentence_id,
                    language_code=lang_code,
                    translation_text=translation_text,
                    verified=False,
                )
            )
        persisted.append(lang_code)

    if source is not None and persisted:
        phase1_sentence = session.get(Sentence, sentence_id)
        log_entity_operation(
            session,
            source=source,
            operation_type=SENTENCE_TRANSLATION_UPDATE,
            entity_guid=phase1_sentence.guid if phase1_sentence else None,
            fact={"languages": sorted(persisted), "phase": 1},
        )

    session.commit()
    logger.info(
        "Persisted Phase-1 translations for sentence %d: %s",
        sentence_id,
        sorted(translations.keys()),
    )


def _clean_word_field(value: Any) -> str:
    """Return a stripped string for a decomposition field, treating None as empty."""
    return str(value or "").strip()


def _optional_word_field(value: Any) -> Optional[str]:
    """Return a stripped string, or None when the field is absent or blank."""
    cleaned = _clean_word_field(value)
    return cleaned or None


def _optional_int_word_field(value: Any) -> Optional[int]:
    """Return an int for a decomposition field, or None when absent/unparsable.

    Bools are rejected explicitly: ``isinstance(True, int)`` is true in Python,
    and a stray boolean head would silently store as 0 or 1.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def store_translation_results(
    sentence_id: int,
    translations: Dict[str, Any],
    session: Session,
    source: Optional[str] = None,
) -> None:
    """
    Store translation results in database.

    Args:
        sentence_id: ID of sentence
        translations: Dict with translation data from LLM
        session: Database session
        source: Who produced these, for the operation log. None skips logging.
    """
    logger.info(f"=== Storing translations for sentence {sentence_id} ===")

    stored_languages: List[str] = []
    word_counts: Dict[str, int] = {}

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
        stored_languages.append(lang_code)

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
        word_counts[lang_code] = len(words_data)
        logger.debug(f"Storing {len(words_data)} words for {lang_code}")

        # Delete existing word links for this language
        session.query(SentenceWord).filter_by(
            sentence_id=sentence_id, language_code=lang_code
        ).delete()

        # Add detailed word records
        for position, word_data in enumerate(words_data):
            # Find matching lemma by GUID if provided. "NONE" is what the prompts
            # ask for when no database lemma matches the word.
            lemma_id = None
            guid = _clean_word_field(word_data.get("lemma_guid"))
            # DEPRECATED: no prompt asks for SYN### ids any more. Kept because a
            # model can still emit the old format from memory, in which case the
            # id must not be looked up -- see SYNTHETIC_GUID_PREFIX in
            # sentences.translate_and_decompose.
            is_synthetic_guid = guid.startswith("SYN") and guid[3:].isdigit()
            if is_synthetic_guid:
                logger.warning(
                    "Deprecated synthetic lemma_guid %r for sentence %s; prompts ask "
                    "for NONE. Treating as unmatched.",
                    guid,
                    sentence_id,
                )
            is_unmatched = guid.lower() in {"none", "null"}

            if guid and not is_synthetic_guid and not is_unmatched:
                # Look up lemma by GUID
                lemma = session.query(Lemma).filter_by(guid=guid).first()
                if lemma:
                    lemma_id = lemma.id

            surface_form = _clean_word_field(word_data.get("surface_form"))

            # Create SentenceWord with detailed grammatical info
            new_word = SentenceWord(
                sentence_id=sentence_id,
                lemma_id=lemma_id,
                language_code=lang_code,
                position=position,
                part_of_speech=_clean_word_field(word_data.get("part_of_speech")),
                english_text=_clean_word_field(word_data.get("english_gloss")),
                target_language_text=surface_form,
                grammatical_form=_optional_word_field(word_data.get("grammatical_form")),
                grammatical_case=None,
                declined_form=surface_form,
                ud_relation=_optional_word_field(word_data.get("ud_relation")),
                ud_head_position=_optional_int_word_field(word_data.get("ud_head_position")),
            )
            session.add(new_word)

    if source is not None:
        # This function writes its rows by hand rather than through
        # storage.crud.sentence_translation, so the logging those functions do
        # never fires here; it has to be done at this level.
        sentence = session.get(Sentence, sentence_id)
        sentence_guid = sentence.guid if sentence else None

        if stored_languages:
            log_entity_operation(
                session,
                source=source,
                operation_type=SENTENCE_TRANSLATION_UPDATE,
                entity_guid=sentence_guid,
                fact={"languages": sorted(stored_languages)},
            )

        for lang_code, count in sorted(word_counts.items()):
            log_batch_operation(
                session,
                source=source,
                operation_type=SENTENCE_WORD_CREATE,
                entity_guid=sentence_guid,
                count=count,
                fact={"language_code": lang_code, "replaced_existing": True},
            )

    session.commit()
    logger.info(f"Stored translation results for sentence {sentence_id}")
