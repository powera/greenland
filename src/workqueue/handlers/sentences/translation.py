"""Capability handlers for sentence translation tasks."""

from __future__ import annotations

from typing import Any, List, Optional

import constants
from storage.models.schema import Sentence, SentenceTranslation
from storage.translation_helpers import (
    get_supported_languages,
    get_tier_1_and_tier_2_languages,
    normalize_llm_language_codes,
)
from sentences.translation import translate_sentence as do_translation
from workqueue.tools import workqueue_payload_handler

_DECOMPOSE_LANGUAGES: List[str] = ["fr", "zh", "lt", "es", "bn", "uk", "kn"]


def do_translate_sentence(
    session: Any,
    sentence_id: int,
    selected_languages: List[str],
    model: str = constants.DEFAULT_MODEL,
    **_: Any,
) -> str:
    """Translate a sentence into selected target languages.

    The sentence must already have at least one SentenceTranslation row; that
    row's language is used as the source language for the LLM prompt. English
    is preferred when present; otherwise the first available translation is
    used. If no English row exists, English is added to the target languages so
    the task always produces one.
    """
    normalized_languages = normalize_llm_language_codes(
        selected_languages,
        operation_name="Workqueue sentence translation",
        all_expansion=get_tier_1_and_tier_2_languages(),
    )

    sentence = session.get(Sentence, sentence_id)
    if not sentence:
        raise ValueError(f"Sentence {sentence_id} not found")

    existing_translations = (
        session.query(SentenceTranslation).filter_by(sentence_id=sentence_id).all()
    )
    if not existing_translations:
        raise ValueError(
            f"Sentence {sentence_id} has no translations; cannot determine source language"
        )

    existing_languages = {t.language_code for t in existing_translations}
    source_language = "en" if "en" in existing_languages else next(iter(existing_languages))

    if "en" not in existing_languages and "en" not in normalized_languages:
        normalized_languages = ["en", *normalized_languages]

    do_translation(
        sentence_id,
        normalized_languages,
        session,
        model=model,
        source_language=source_language,
    )

    language_names = [
        get_supported_languages().get(language_code, language_code)
        for language_code in normalized_languages
    ]
    return (
        f"Successfully translated sentence (source={source_language}) to: "
        f"{', '.join(language_names)}"
    )


@workqueue_payload_handler()
def handle_sentences_translate(
    session: Any,
    sentence_id: Optional[int] = None,
    sentence_ids: Optional[List[int]] = None,
    selected_languages: Optional[List[str]] = None,
    model: str = constants.DEFAULT_MODEL,
    batch: bool = False,
) -> str:
    """Workqueue wrapper for sentence translation.

    Accepts either a single ``sentence_id`` or a list ``sentence_ids`` for
    batch processing queued by ``/api/llm/sentences/decompose``.
    ``selected_languages`` defaults to the standard decomposition set
    (fr, zh, lt, es) when omitted; English word breakdown is produced
    automatically by ``do_translate_sentence`` when no English words exist.
    """
    languages = selected_languages if selected_languages is not None else _DECOMPOSE_LANGUAGES
    if sentence_ids:
        results = [
            do_translate_sentence(
                session=session,
                sentence_id=sid,
                selected_languages=languages,
                model=model,
            )
            for sid in sentence_ids
        ]
        return f"Batch completed for {len(sentence_ids)} sentences: " + "; ".join(results)
    if sentence_id is None:
        raise ValueError("sentence_id or sentence_ids is required")
    return do_translate_sentence(
        session=session,
        sentence_id=sentence_id,
        selected_languages=languages,
        model=model,
    )
