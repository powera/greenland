"""Capability handlers for word translation tasks.

``TRANSLATIONS_JOB`` is voras's populate as a staged job for OpenAI batches
(``voras --populate --batch``), one item per lemma and group of at most 10
missing languages, built from the same pieces as the live path
(``words.translation_populate``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy.orm import Session

from clients.types import LLMCall

import constants
from barsukas.config import Config
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.operation_log import log_operation
from storage.models.schema import Lemma
from storage.translation_helpers import (
    LANGUAGE_FIELDS,
    convert_llm_response_to_translation_metadata,
    get_reference_translation,
    get_translation,
    lang_code_to_llm_field,
    normalize_llm_language_codes,
    split_llm_language_batches,
)
from wordfreq.translation.client import LinguisticClient
from words.translation_populate import (
    build_populate_call,
    missing_translation_languages,
    populate_groups,
    populate_reference,
    store_populated_translations,
)
from words.translation_workflow import TranslationWorkflow
from workqueue.llm_batch import Done, Job, Next, Ready, Stage, StageContext
from workqueue.tools import workqueue_payload_handler


def _build_config(model: Optional[str] = None) -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=model or constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )


def do_generate_missing_translations(
    session: Any,
    lemma_id: int,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Generate missing translations for a lemma, optionally constrained to languages."""
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    requested_languages = normalize_llm_language_codes(
        languages or list(LANGUAGE_FIELDS.keys()),
        operation_name="Workqueue word translation",
        max_languages=len(LANGUAGE_FIELDS),
    )
    missing_languages: List[str] = []
    for language_code in requested_languages:
        translation = get_translation(session, lemma, language_code)
        if not translation or not translation.strip():
            missing_languages.append(language_code)

    if not missing_languages:
        return "No missing translations to generate"

    reference_lang_code, reference_translation = get_reference_translation(
        session, lemma, exclude_languages=missing_languages
    )
    if not reference_translation:
        reference_lang_code = "en"
        reference_translation = lemma.lemma_text

    config = _build_config(model)
    workflow = TranslationWorkflow(config=config)
    client = LinguisticClient(
        model=config.model or "",
        db_path=config.sqlite_path or "",
        debug=Config.DEBUG,
    )
    translations: Dict[str, Any] = {}
    for language_batch in split_llm_language_batches(missing_languages):
        batch_translations, success = client.query_translations(
            english_word=lemma.lemma_text,
            reference_translation=(
                reference_lang_code or "en",
                reference_translation or lemma.lemma_text,
            ),
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            languages=language_batch,
        )
        if not success or not batch_translations:
            raise RuntimeError(
                "LLM could not generate translations for " + ", ".join(language_batch)
            )
        translations.update(batch_translations)

    translation_metadata_by_lang_code = convert_llm_response_to_translation_metadata(translations)
    added_count = 0
    for language_code in missing_languages:
        llm_field = lang_code_to_llm_field(language_code)
        if llm_field:
            response_value = translations.get(llm_field, "")
            if isinstance(response_value, dict):
                raw_translation = response_value.get("translation", "")
                translation_text = (
                    raw_translation.strip() if isinstance(raw_translation, str) else ""
                )
            else:
                translation_text = response_value.strip() if isinstance(response_value, str) else ""
            if translation_text:
                translation_metadata = translation_metadata_by_lang_code.get(language_code, {})
                workflow.set_translation(
                    session,
                    lemma,
                    language_code,
                    translation_text,
                    translation_status=translation_metadata.get("translation_status"),
                    translation_status_note=translation_metadata.get("translation_status_note"),
                )
                added_count += 1

    log_operation(
        session,
        operation_type="translations_populated",
        entity_type="lemma",
        entity_id=lemma.id,
        details={
            "languages": missing_languages,
            "count": added_count,
            "task": "words.translations",
            "model": config.model,
            "via_worker": True,
        },
    )
    session.commit()
    return f"Added {added_count} translation(s) for {', '.join(missing_languages)}"


def do_regenerate_translations(session: Any, lemma_id: int, **_: Any) -> str:
    """Regenerate all non-Lithuanian translations for a lemma."""
    lemma = session.get(Lemma, lemma_id)
    if not lemma:
        raise ValueError(f"Lemma {lemma_id} not found")

    config = _build_config()
    workflow = TranslationWorkflow(config=config)
    client = LinguisticClient(
        model=config.model or "",
        db_path=config.sqlite_path or "",
        debug=Config.DEBUG,
    )

    languages_to_regenerate = [
        language_code for language_code in LANGUAGE_FIELDS if language_code != "lt"
    ]
    for language_code in languages_to_regenerate:
        setattr(lemma, LANGUAGE_FIELDS[language_code][0], None)

    session.flush()

    reference_lang_code, reference_translation = get_reference_translation(
        session, lemma, exclude_languages=languages_to_regenerate
    )
    if not reference_translation:
        reference_lang_code = "en"
        reference_translation = lemma.lemma_text

    translations: Dict[str, Any] = {}
    for language_batch in split_llm_language_batches(languages_to_regenerate):
        batch_translations, success = client.query_translations(
            english_word=lemma.lemma_text,
            reference_translation=(
                reference_lang_code or "en",
                reference_translation or lemma.lemma_text,
            ),
            definition=lemma.definition_text,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            languages=language_batch,
        )
        if not success or not batch_translations:
            raise RuntimeError(
                "LLM could not regenerate translations for " + ", ".join(language_batch)
            )
        translations.update(batch_translations)

    regenerated_count = 0
    for language_code in languages_to_regenerate:
        llm_field = lang_code_to_llm_field(language_code)
        if llm_field:
            translation_text = translations.get(llm_field, "").strip()
            if translation_text:
                workflow.set_translation(session, lemma, language_code, translation_text)
                regenerated_count += 1

    log_operation(
        session,
        operation_type="translations_regenerated",
        entity_type="lemma",
        entity_id=lemma.id,
        details={
            "languages": languages_to_regenerate,
            "count": regenerated_count,
            "task": "words.translations.regenerate",
            "model": config.model,
            "via_worker": True,
        },
    )
    session.commit()
    return f"Regenerated {regenerated_count} translation(s)"


@workqueue_payload_handler()
def handle_words_translations(
    session: Any,
    lemma_id: Optional[int] = None,
    lemma_ids: Optional[List[int]] = None,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
    **_: Any,
) -> str:
    """Workqueue wrapper for missing translation generation."""
    if lemma_ids:
        results = [
            do_generate_missing_translations(
                session=session,
                lemma_id=queued_lemma_id,
                languages=languages,
                model=model,
            )
            for queued_lemma_id in lemma_ids
        ]
        return f"Batch completed for {len(lemma_ids)} lemmas: " + "; ".join(results)
    if lemma_id is None:
        raise ValueError("lemma_id or lemma_ids is required")
    return do_generate_missing_translations(
        session=session, lemma_id=lemma_id, languages=languages, model=model
    )


@workqueue_payload_handler()
def handle_words_translations_regenerate(session: Any, lemma_id: int, **_: Any) -> str:
    """Workqueue wrapper for translation regeneration.

    Accepts and ignores extra payload kwargs (``model``, etc.) added by the
    route so it is tolerant of payload changes.
    """
    return do_regenerate_translations(session=session, lemma_id=lemma_id)


# ---------------------------------------------------------------------------
# Staged-job form, for batching (see workqueue.llm_batch)
# ---------------------------------------------------------------------------

TRANSLATIONS_JOB_NAME = "voras"
TRANSLATIONS_STAGE = "translations.populate"


def translation_populate_states(
    session: Session, lemmas: Sequence[Lemma], languages: Sequence[str]
) -> Tuple[List[Dict[str, Any]], int]:
    """Item states for every lemma's missing languages, at most 10 languages each.

    Returns:
        ``(states, lemmas with nothing missing)``.
    """
    states: List[Dict[str, Any]] = []
    complete = 0
    for lemma in lemmas:
        missing = missing_translation_languages(session, lemma, languages)
        if not missing:
            complete += 1
            continue
        states.extend(
            {"lemma_id": lemma.id, "languages": group} for group in populate_groups(missing)
        )
    return states, complete


def _prepare_populate(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    missing = missing_translation_languages(session, lemma, state["languages"])
    if not missing:
        return Done("skipped", "translations already present")
    reference = populate_reference(session, lemma, missing)
    if reference is None:
        return Done("rejected", "no reference translation")
    call = build_populate_call(lemma, reference, missing)
    if call is None:
        return Done("rejected", "could not build a prompt")
    state["asked"] = missing
    return call


def _apply_populate(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", f"Lemma {state['lemma_id']} not found")
    written, blank = store_populated_translations(
        session, lemma, data, state["asked"], source=f"voras-agent/batch/{ctx.model}"
    )
    if written:
        return Done("written", ", ".join(written))
    if blank:
        return Done("rejected", f"blank answer for {', '.join(blank)}")
    return Done("skipped", "translations already present")


TRANSLATIONS_JOB = Job(
    name=TRANSLATIONS_JOB_NAME,
    stages=(Stage(TRANSLATIONS_STAGE, _prepare_populate, _apply_populate),),
    item_key=lambda state: f"{state['lemma_id']}:{'+'.join(state['languages'])}",
)
