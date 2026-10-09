"""Capability handlers for sentence translation tasks.

``SENTENCE_TRANSLATION_JOB`` is the sentence pipeline as a staged job for
OpenAI batches, built from the live path's own plan, requests and storage:

1. ``sentences.translate``: Phase 1, persisted before anything else.
2. ``sentences.decompose``: Phase 2 (candidate lookup) and Phase 3 (the combined
   decomposition), prepared once every sentence of the run has its Phase-1
   translations.

The optional Phase-4 dependency pass is not part of it.  Translate-only and
decompose-only requests skip the stage they do not need.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

import constants
from clients.batch_queue import BatchQueueManager
from clients.types import LLMCall
from storage.models.schema import Sentence, SentenceTranslation
from storage.translation_helpers import (
    get_supported_languages,
    get_tier_1_and_tier_2_languages,
    normalize_llm_language_codes,
)
from sentences.translate_and_decompose import (
    build_phase1_call,
    build_phase3_request,
    interpret_phase1,
    interpret_phase1_confidences,
    interpret_phase3,
    plan_phase3,
)
from sentences.translation import (
    SentenceTranslationPlan,
    persist_phase1_translations,
    plan_sentence_translation,
    store_decomposition_results,
)
from sentences.translation import translate_sentence as do_translation
from sentences.translation_coverage import translate_sentence_simple
from workqueue.llm_batch import (
    Done,
    Job,
    Next,
    Ready,
    RunReport,
    Stage,
    StageContext,
    start_batch_run,
)
from workqueue.tools import workqueue_payload_handler

_DECOMPOSE_LANGUAGES: List[str] = ["fr", "zh", "lt", "es", "es-419"]


def do_translate_sentence(
    session: Any,
    sentence_id: int,
    selected_languages: List[str],
    model: str = constants.DEFAULT_MODEL,
    retry_uncertain: bool = False,
    **_: Any,
) -> str:
    """Translate a sentence into selected target languages.

    Languages a model was uncertain of are skipped unless ``retry_uncertain``
    (see sentences.translation.plan_sentence_translation).  This queue serves
    zvirblis's bulk runs, so it skips them by default, unlike the per-item
    forms and pronunciation queues.

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
        retry_uncertain=retry_uncertain,
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
    retry_uncertain: bool = False,
    **_: Any,
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
                retry_uncertain=retry_uncertain,
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
        retry_uncertain=retry_uncertain,
    )


@workqueue_payload_handler()
def handle_sentences_translate_simple(
    session: Any,
    sentence_id: int,
    selected_languages: Optional[List[str]] = None,
    **_: Any,
) -> str:
    """Add missing text-only translations to one sentence with TranslateGemma."""
    languages = selected_languages if selected_languages is not None else _DECOMPOSE_LANGUAGES
    normalized_languages = normalize_llm_language_codes(
        languages,
        operation_name="Workqueue simple sentence translation",
        all_expansion=get_tier_1_and_tier_2_languages(),
    )
    added_count = translate_sentence_simple(
        session,
        sentence_id=sentence_id,
        target_languages=normalized_languages,
    )
    return f"Added {added_count} text-only translations to sentence {sentence_id}"


# ---------------------------------------------------------------------------
# Staged-job form, for batching (see workqueue.llm_batch)
# ---------------------------------------------------------------------------

SENTENCE_TRANSLATION_JOB_NAME = "zvirblis"
TRANSLATE_STAGE = "sentences.translate"
DECOMPOSE_STAGE = "sentences.decompose"

# Ready marker: the item needs no Phase 1 (decompose only, or nothing missing).
_NO_PHASE1 = "__no_phase1__"


def sentence_translation_state(
    sentence_id: int,
    target_languages: List[str],
    *,
    translate: bool = True,
    decompose: bool = True,
    decompose_languages: Optional[List[str]] = None,
    skip_existing_translations: bool = False,
    log_source: Optional[str] = None,
    retry_uncertain: bool = False,
) -> Dict[str, Any]:
    """The item state the sentence job works on.

    Args:
        target_languages: Requested languages (Phase 1 targets).
        translate: Run Phase 1.  False for a decompose-only request.
        decompose: Run Phases 2+3.  False for a translate-only request.
        decompose_languages: Languages to decompose; None for the live path's
            rule (the requested languages, plus English while it has no words).
        skip_existing_translations: Leave out of Phase 1 the languages the
            sentence already has.
        log_source: Who is running this, for the operation log.
        retry_uncertain: Also ask for languages a model was uncertain of before.
    """
    return {
        "sentence_id": sentence_id,
        "target_languages": list(target_languages),
        "translate": translate,
        "decompose": decompose,
        "decompose_languages": decompose_languages,
        "skip_existing_translations": skip_existing_translations,
        "log_source": log_source,
        "retry_uncertain": retry_uncertain,
    }


def _plan(session: Session, state: Dict[str, Any]) -> SentenceTranslationPlan:
    return plan_sentence_translation(
        session,
        state["sentence_id"],
        state["target_languages"],
        skip_existing_translations=bool(state.get("skip_existing_translations")),
        retry_uncertain=bool(state.get("retry_uncertain")),
    )


def _prepare_translate(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    """Stage 1 (Phase 1): sentence-level translation."""
    try:
        plan = _plan(session, state)
    except ValueError as error:
        return Done("rejected", str(error))
    if not state.get("translate", True) or not plan.phase1_languages:
        if not state.get("decompose", True):
            return Done("skipped", "nothing to translate")
        return Ready({_NO_PHASE1: True})
    built = build_phase1_call(
        sentence_text=plan.source_text,
        source_language=plan.source_language,
        target_languages=plan.phase1_languages,
        conversation_context=plan.conversation_context,
    )
    if built is None:
        return Ready({_NO_PHASE1: True}) if state.get("decompose", True) else Done("rejected")
    call, normalized_targets = built
    state["phase1_languages"] = normalized_targets
    return call


def _apply_translate(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    translated = 0
    uncertain: List[str] = []
    if not data.get(_NO_PHASE1):
        phase1_languages = state.get("phase1_languages") or []
        translations = interpret_phase1(data, phase1_languages)
        if not translations:
            return Done("failed", "Phase 1 translation produced no results")
        # Persisted before Phase 3, as the live path does.  Stage 2 reads the
        # stored rows, so an uncertain answer is not decomposed either.
        uncertain = persist_phase1_translations(
            state["sentence_id"],
            translations,
            session,
            source=state.get("log_source"),
            confidences=interpret_phase1_confidences(data, phase1_languages),
            model=ctx.model,
        )
        translated = len(translations) - len(uncertain)
    if not state.get("decompose", True):
        if translated == 0 and uncertain:
            return Done("rejected", f"below confidence: {', '.join(uncertain)}")
        suffix = f"; uncertain: {', '.join(uncertain)}" if uncertain else ""
        return Done("written", f"{translated} translation(s){suffix}")
    return Next({key: value for key, value in state.items() if key != "phase1_languages"})


def _prepare_decompose(
    session: Session, state: Dict[str, Any], ctx: StageContext
) -> Union[LLMCall, Ready, Done]:
    """Stage 2 (Phases 2+3): candidate lookup, then the combined decomposition."""
    try:
        plan = _plan(session, state)
    except ValueError as error:
        return Done("rejected", str(error))
    translations = {
        row.language_code: row.translation_text
        for row in session.query(SentenceTranslation)
        .filter_by(sentence_id=state["sentence_id"])
        .all()
        if row.language_code != plan.source_language
    }
    explicit = state.get("decompose_languages")
    phase3 = plan_phase3(
        session=session,
        sentence_text=plan.source_text,
        source_language=plan.source_language,
        translations=translations,
        decompose_languages=explicit if explicit is not None else plan.decompose_languages,
    )
    if not phase3.target_translations:
        errors = sorted({failure.error or "" for failure in phase3.failures.values()})
        return Done("rejected", "; ".join(errors) or "nothing to decompose")
    state["source_language"] = plan.source_language
    state["target_translations"] = phase3.target_translations
    return build_phase3_request(
        source_sentence=phase3.anchor_text,
        source_language=phase3.anchor_language,
        target_translations=phase3.target_translations,
        helper_translations=phase3.helper_translations,
        candidate_lemmas=phase3.candidate_lemmas,
    )


def _apply_decompose(
    session: Session, state: Dict[str, Any], data: Dict[str, Any], ctx: StageContext
) -> Union[Done, Next]:
    decompositions = interpret_phase3(data, state["target_translations"], ctx.model)
    stored = store_decomposition_results(
        session, state["sentence_id"], {}, decompositions, source=state.get("log_source")
    )
    if stored:
        return Done("written", f"words for {', '.join(stored)}")
    errors = sorted({d.error or "" for d in decompositions.values() if not d.success})
    return Done("failed", "; ".join(errors))


SENTENCE_TRANSLATION_JOB = Job(
    name=SENTENCE_TRANSLATION_JOB_NAME,
    stages=(
        Stage(TRANSLATE_STAGE, _prepare_translate, _apply_translate),
        Stage(DECOMPOSE_STAGE, _prepare_decompose, _apply_decompose),
    ),
    item_key=lambda state: (
        f"{state['sentence_id']}:{int(bool(state.get('translate', True)))}"
        f"{int(bool(state.get('decompose', True)))}"
    ),
    entity_type="sentence",
    entity_id_key="sentence_id",
)


def submit_sentence_translation_batch(
    session: Session,
    states: List[Dict[str, Any]],
    model: str,
    manager: Optional[BatchQueueManager] = None,
) -> RunReport:
    """Start a batch run of the sentence job; the entry point the workqueue
    handlers and zvirblis's ``submit-batch`` share."""
    from clients.batch_queue import create_batch_database_session
    from clients.openai.batch_client import OpenAIBatchClient

    if manager is not None:
        return start_batch_run(session, manager, SENTENCE_TRANSLATION_JOB, states, model)
    batch_session = create_batch_database_session()
    try:
        batch_manager = BatchQueueManager(batch_session, OpenAIBatchClient())
        return start_batch_run(session, batch_manager, SENTENCE_TRANSLATION_JOB, states, model)
    finally:
        batch_session.close()


def describe_run(report: RunReport) -> str:
    """One line for a workqueue task result."""
    text = f"Run {report.run_id}: {report.calls} request(s)"
    if report.batch_ids:
        text += f" in {', '.join(report.batch_ids)}"
    if report.skipped_in_flight:
        text += f"; {report.skipped_in_flight} already in a run"
    if report.resolved_without_llm:
        text += "; " + ", ".join(
            f"{count} {outcome}" for outcome, count in sorted(report.resolved_without_llm.items())
        )
    return text
