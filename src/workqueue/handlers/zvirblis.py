"""Workqueue handler for sentence translation tasks.

This module implements the handle_translate_sentence function that is called
by the Barsukas task worker when processing TRANSLATE_SENTENCE tasks.
"""

from __future__ import annotations

from typing import Dict

from sqlalchemy.orm import Session

from workqueue.tools import get_lemma_or_raise
import constants
from wordfreq.storage.models.schema import Sentence, SentenceTranslation
from wordfreq.storage.translation_helpers import get_supported_languages
from sentences.translation import translate_sentence as do_translation


def handle_translate_sentence(session: Session, payload: Dict) -> str:
    """
    Handle sentence translation task.

    Payload schema:
        sentence_id: int - ID of the sentence to translate
        selected_languages: List[str] - Language codes to translate to

    Returns:
        str: Result message describing what was translated
    """
    sentence_id = payload["sentence_id"]
    selected_languages = payload["selected_languages"]

    sentence = session.get(Sentence, sentence_id)
    if not sentence:
        raise ValueError(f"Sentence {sentence_id} not found")

    # Check if sentence has English translation
    en_translation = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .first()
    )

    if not en_translation:
        raise ValueError(
            "Sentence must have an English translation before translating to other languages"
        )

    # Use the shared translation logic
    do_translation(sentence_id, selected_languages, session, model=constants.DEFAULT_MODEL)

    lang_names = [get_supported_languages().get(lang, lang) for lang in selected_languages]
    return f"Successfully translated sentence to: {', '.join(lang_names)}"
