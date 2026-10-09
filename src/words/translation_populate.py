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
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from clients.types import LLMCall
from storage.models.schema import Lemma
from storage.translation_helpers import (
    convert_llm_response_to_confidences,
    convert_llm_response_to_lang_codes,
    convert_llm_response_to_translation_metadata,
    get_reference_translation,
    get_translation,
    split_llm_language_batches,
)
from wordfreq.translation.translations import build_translation_prompt
from words.lemma_creation import store_llm_translation

logger = logging.getLogger(__name__)


def missing_translation_languages(
    session: Session, lemma: Lemma, languages: Sequence[str], retry_uncertain: bool = False
) -> List[str]:
    """The languages among *languages* the lemma has no (non-blank) translation for.

    A language a model was uncertain of (see
    words.lemma_creation.store_llm_translation) is left out unless
    *retry_uncertain*: asked again without its context, a model fills the gap
    with the term it doubted, or a worse one.
    """
    missing = [
        language_code
        for language_code in languages
        if not (get_translation(session, lemma, language_code) or "").strip()
    ]
    if retry_uncertain:
        return missing
    uncertain = uncertain_translation_languages(session, lemma, missing)
    return [language_code for language_code in missing if language_code not in uncertain]


def uncertain_translation_languages(
    session: Session, lemma: Lemma, languages: Sequence[str]
) -> List[str]:
    """The languages among *languages* a model was uncertain of for this lemma."""
    return [
        language_code
        for language_code in languages
        if store_llm_translation.is_uncertain(session, lemma=lemma, lang_code=language_code)
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


class PopulateOutcome(NamedTuple):
    """What :func:`store_translations_by_language` did with each language."""

    written: List[str]
    #: The answer left these blank.
    blank: List[str]
    #: Below the confidence floor: recorded in uncertain_llm_results instead.
    uncertain: List[str]


def store_populated_translations(
    session: Session,
    lemma: Lemma,
    llm_response: Dict[str, Any],
    languages: Sequence[str],
    source: str,
    model: Optional[str] = None,
) -> PopulateOutcome:
    """Write a translation answer (LLM field names) for *languages*; the caller commits.

    Each language's own confidence gates its translation; see
    :func:`store_translations_by_language`.
    """
    return store_translations_by_language(
        session,
        lemma,
        convert_llm_response_to_lang_codes(llm_response),
        convert_llm_response_to_translation_metadata(llm_response),
        languages,
        source,
        confidences=convert_llm_response_to_confidences(llm_response),
        model=model,
    )


def store_translations_by_language(
    session: Session,
    lemma: Lemma,
    texts: Dict[str, str],
    metadata: Dict[str, Dict[str, Any]],
    languages: Sequence[str],
    source: str,
    confidences: Optional[Dict[str, Optional[float]]] = None,
    model: Optional[str] = None,
) -> PopulateOutcome:
    """Write language-code-keyed translations for *languages*; the caller commits.

    The one writer for filled-in translations, live or batched.  A language
    that has gained a translation since it was found missing (added by hand
    while a batch ran, say) is left alone.

    A language in *confidences* is gated on its confidence (a missing or
    non-numeric one counts as 0.0) through
    words.lemma_creation.store_llm_translation, which records one below the
    floor as uncertain.  A language absent from it -- an answer that was never
    asked to rate itself, such as a batch sent before the field existed, or a
    cached translation -- is stored as it is.
    """
    outcome = PopulateOutcome([], [], [])
    for language_code in languages:
        text = (texts.get(language_code) or "").strip()
        if not text:
            outcome.blank.append(language_code)
            continue
        if (get_translation(session, lemma, language_code) or "").strip():
            continue
        language_metadata = metadata.get(language_code, {})
        confidence: Optional[float] = None
        if confidences is not None and language_code in confidences:
            confidence = confidences[language_code] or 0.0
        stored = store_llm_translation(
            session,
            lemma,
            language_code,
            text,
            source=source,
            translation_status=language_metadata.get("translation_status"),
            translation_status_note=language_metadata.get("translation_status_note"),
            confidence=confidence,
            model=model,
        )
        if stored is None:
            outcome.uncertain.append(language_code)
        else:
            outcome.written.append(language_code)
    return outcome
