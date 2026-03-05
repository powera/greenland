"""Capability handlers for sentence translation tasks."""

from __future__ import annotations

from typing import Any, List

import constants
from storage.models.schema import Sentence, SentenceTranslation
from storage.translation_helpers import (
    get_supported_languages,
    get_tier_1_and_tier_2_languages,
    normalize_llm_language_codes,
)
from sentences.translation import translate_sentence as do_translation
from workqueue.tools import workqueue_payload_handler


def do_translate_sentence(
    session: Any,
    sentence_id: int,
    selected_languages: List[str],
    **_: Any,
) -> str:
    """Translate a sentence into selected target languages."""
    normalized_languages = normalize_llm_language_codes(
        selected_languages,
        operation_name="Workqueue sentence translation",
        all_expansion=get_tier_1_and_tier_2_languages(),
    )

    sentence = session.get(Sentence, sentence_id)
    if not sentence:
        raise ValueError(f"Sentence {sentence_id} not found")

    en_translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .first()
    )
    if not en_translation:
        raise ValueError(
            "Sentence must have an English translation before translating to other languages"
        )

    do_translation(sentence_id, normalized_languages, session, model=constants.DEFAULT_MODEL)

    language_names = [
        get_supported_languages().get(language_code, language_code)
        for language_code in normalized_languages
    ]
    return f"Successfully translated sentence to: {', '.join(language_names)}"


@workqueue_payload_handler()
def handle_sentences_translate(
    session: Any,
    sentence_id: int,
    selected_languages: List[str],
) -> str:
    """Workqueue wrapper for sentence translation."""
    return do_translate_sentence(
        session=session,
        sentence_id=sentence_id,
        selected_languages=selected_languages,
    )
