"""Filling a lemma's missing translations: the pieces voras's live and batch paths share.

The live path (``TranslationWorkflow.fix_missing_translations``) and the batch
job (``workqueue.handlers.words.translations.TRANSLATIONS_JOB``) both:

1. find the languages a lemma lacks (:func:`missing_translation_languages`),
   split into groups of at most 10 (``split_llm_language_batches``);
2. pick a reference translation, or skip the lemma when it has none
   (:func:`populate_reference`);
3. send the request :func:`build_populate_call` builds; and
4. write the answer with :func:`store_populated_translations`.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from clients.types import LLMCall
from storage.crud.operation_log import log_translation_change
from storage.models.schema import Lemma
from storage.translation_helpers import (
    convert_llm_response_to_lang_codes,
    convert_llm_response_to_translation_metadata,
    get_reference_translation,
    get_translation,
    set_translation,
    split_llm_language_batches,
)
from wordfreq.translation.translations import build_translation_prompt

logger = logging.getLogger(__name__)


def missing_translation_languages(
    session: Session, lemma: Lemma, languages: Sequence[str]
) -> List[str]:
    """The languages among *languages* the lemma has no (non-blank) translation for."""
    return [
        language_code
        for language_code in languages
        if not (get_translation(session, lemma, language_code) or "").strip()
    ]


def populate_reference(
    session: Session, lemma: Lemma, missing: Sequence[str]
) -> Optional[Tuple[str, str]]:
    """``(language, translation)`` to anchor the request on, or None to skip the lemma."""
    reference_lang_code, reference_text = get_reference_translation(
        session, lemma, exclude_languages=list(missing)
    )
    if not reference_lang_code or not reference_text:
        return None
    return reference_lang_code, reference_text


def build_populate_call(
    lemma: Lemma, reference: Tuple[str, str], languages: Sequence[str]
) -> Optional[LLMCall]:
    """The translation request for *languages* (at most 10), or None if none can be built."""
    prompt = build_translation_prompt(
        lemma.lemma_text,
        reference,
        lemma.definition_text,
        lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        languages=list(languages),
    )
    if prompt is None:
        return None
    return LLMCall(prompt=prompt.prompt, schema=prompt.schema, context=prompt.context)


def populate_groups(missing: Sequence[str]) -> List[List[str]]:
    """Split missing languages into the groups one request each covers."""
    return [list(group) for group in split_llm_language_batches(list(missing))]


def store_populated_translations(
    session: Session,
    lemma: Lemma,
    llm_response: Dict[str, Any],
    languages: Sequence[str],
    source: str,
) -> Tuple[List[str], List[str]]:
    """Write a translation answer (LLM field names) for *languages*; the caller commits.

    Returns:
        ``(languages written, languages the answer left blank)``.
    """
    return store_translations_by_language(
        session,
        lemma,
        convert_llm_response_to_lang_codes(llm_response),
        convert_llm_response_to_translation_metadata(llm_response),
        languages,
        source,
    )


def store_translations_by_language(
    session: Session,
    lemma: Lemma,
    texts: Dict[str, str],
    metadata: Dict[str, Dict[str, Any]],
    languages: Sequence[str],
    source: str,
) -> Tuple[List[str], List[str]]:
    """Write language-code-keyed translations for *languages*; the caller commits.

    The one writer for filled-in translations, live or batched.  A language
    that has gained a translation since it was found missing (added by hand
    while a batch ran, say) is left alone.

    Returns:
        ``(languages written, languages the answer left blank)``.
    """
    written: List[str] = []
    blank: List[str] = []
    for language_code in languages:
        text = (texts.get(language_code) or "").strip()
        if not text:
            blank.append(language_code)
            continue
        if (get_translation(session, lemma, language_code) or "").strip():
            continue
        language_metadata = metadata.get(language_code, {})
        old_translation, new_translation = set_translation(
            session,
            lemma,
            language_code,
            text,
            translation_status=language_metadata.get("translation_status"),
            translation_status_note=language_metadata.get("translation_status_note"),
        )
        log_translation_change(
            session=session,
            source=source,
            operation_type="translation",
            lemma_id=lemma.id,
            language_code=language_code,
            old_translation=old_translation,
            new_translation=new_translation,
        )
        written.append(language_code)
    return written, blank
