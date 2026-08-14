"""The ``sentences.import`` capability: run one sentence through the import path.

This is the single owner of the sentence import path. It runs the stages in
:mod:`sentences.import_workflow` in order -- translate, decompose, annotate,
link, stage, promote, finalize -- deciding what to do next by reading the
database rather than by consulting stored progress. A retry is therefore just
"run it again": whatever is already done is skipped.

Stages run **inline**, in one task execution, rather than as a chain of tasks
that each enqueue the next. The worker claims one task at a time and sleeps
between claims, so a chain would cost a claim/commit round trip and a poll
interval per stage, on a queue shared with word and audio work. Running inline
also means one session and one warm LLM client for the whole sentence.

The one place the task yields is the promote/link boundary. Promotion is
human-gated by default, and waiting for a human inside a worker slot would pin
it indefinitely. So after promotion the task re-enqueues *itself* with an
incremented iteration and exits, and the next run picks up the newly created
lemmas at the link stage.

That loop terminates on three independent guards, any one of which is enough:
an iteration cap, a progress fingerprint that stops the loop as soon as an
iteration changes nothing, and the fact that a blocked stage counts as settled
so the sequencer never sits on a stage that cannot proceed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import constants
from clients.unified_client import UnifiedLLMClient
from sentences.import_workflow import (
    SentenceImportSpec,
    SentenceImportStage,
    evaluate_stage,
    next_incomplete_stage,
    progress_fingerprint,
    unlinked_words,
)
from sentences.link_writer import link_sentence_words
from sentences.pending_staging import stage_unlinked_words
from sentences.promotion import PromotionPolicy, promote_sentence_pendings
from storage.backend.config import DataSourceConfig
from storage.crud.sentence import calculate_minimum_level
from storage.models.schema import Sentence, SentenceTranslation
from workqueue.task_queue import enqueue_task
from workqueue.tools import workqueue_payload_handler

logger = logging.getLogger(__name__)

TASK_TYPE: str = "sentences.import"

# Stages that can consume an LLM call, for the summary line.
_LLM_STAGES = {
    SentenceImportStage.TRANSLATE,
    SentenceImportStage.DECOMPOSE,
    SentenceImportStage.ANNOTATE,
    SentenceImportStage.PROMOTE,
}


def _source_language(session: Any, sentence_id: int) -> str:
    """Language to translate from: English when present, else any existing row."""
    languages = {
        str(row[0])
        for row in session.query(SentenceTranslation.language_code)
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .all()
        if row[0]
    }
    if not languages:
        raise ValueError(f"Sentence {sentence_id} has no translation to work from")
    return "en" if "en" in languages else sorted(languages)[0]


def _run_translate(session: Any, sentence_id: int, spec: SentenceImportSpec, status: Any) -> str:
    """Phase 1 + Phase 2/3: translate into the missing languages and decompose.

    Delegates to ``sentences.translation.translate_sentence``, which is the same
    function the ``sentences.translate`` task uses and which persists both the
    translations and the per-language word breakdowns.
    """
    from sentences.translation import translate_sentence

    missing: List[str] = list(status.detail.get("missing_languages") or [])
    if not missing:
        return "translate: nothing missing"

    produced = translate_sentence(
        sentence_id,
        missing,
        session,
        model=spec.model,
        source_language=_source_language(session, sentence_id),
    )
    return f"translate: +{len(produced)} language(s)"


def _run_decompose(
    session: Any,
    sentence_id: int,
    spec: SentenceImportSpec,
    status: Any,
    client: UnifiedLLMClient,
) -> str:
    """Decompose languages that have a translation but no word rows.

    ``translate_sentence`` decomposes what it translates, so this only fires
    when a translation arrived by some other route -- an import, or a human
    curating the text by hand. It therefore runs Phase 2/3 against the stored
    translations only: going back through ``translate_sentence`` would re-run
    Phase 1 and overwrite that stored text (including rows a human has marked
    verified) with a fresh machine translation.
    """
    from sentences.translate_and_decompose import decompose_with_existing_translations

    missing: List[str] = list(status.detail.get("missing_languages") or [])
    if not missing:
        return "decompose: nothing missing"

    source_language = _source_language(session, sentence_id)
    stored: Dict[str, str] = {
        str(row[0]): str(row[1])
        for row in session.query(
            SentenceTranslation.language_code, SentenceTranslation.translation_text
        )
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .all()
        if row[0] and row[1]
    }
    source_text = stored.pop(source_language, "")

    result = decompose_with_existing_translations(
        sentence_text=source_text,
        source_language=source_language,
        translations=stored,
        session=session,
        client=client,
        decompose_languages=missing,
        model=spec.model,
    )

    # Persist word rows only. Passing the translation texts back through
    # store_translation_results would rewrite them from the decomposition
    # output, which is exactly what this stage must not do.
    word_payload: Dict[str, Any] = {}
    decomposed: List[str] = []
    for language_code, decomposition in result.decompositions.items():
        if not decomposition.success:
            logger.warning(
                "Sentence %s: decomposition failed for %s: %s",
                sentence_id,
                language_code,
                decomposition.error,
            )
            continue
        word_payload[f"words_{language_code}"] = list(decomposition.words)
        decomposed.append(language_code)

    if word_payload:
        from sentences.translation import store_translation_results

        store_translation_results(sentence_id, word_payload, session)
    return f"decompose: {len(decomposed)} language(s)"


def _run_annotate(
    session: Any,
    sentence_id: int,
    spec: SentenceImportSpec,
    client: UnifiedLLMClient,
) -> str:
    """Phase 4: add Universal Dependencies relations to the stored words.

    Rebuilds a decomposition object from the stored rows because Phase 4 numbers
    heads by token position, and the stored rows are the authoritative
    numbering once the words have been persisted.
    """
    from sentences.translate_and_decompose import (
        DecomposedLanguage,
        annotate_language_dependencies,
    )
    from storage.models.schema import SentenceWord

    annotated_languages = 0
    for language_code in spec.decompose_languages:
        rows = (
            session.query(SentenceWord)
            .filter(
                SentenceWord.sentence_id == sentence_id,
                SentenceWord.language_code == language_code,
            )
            .order_by(SentenceWord.position)
            .all()
        )
        if not rows or all(row.ud_relation for row in rows):
            continue

        translation = (
            session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence_id, language_code=language_code)
            .first()
        )
        decomposition = DecomposedLanguage(
            language_code=language_code,
            translation=translation.translation_text if translation else "",
            words=[
                {
                    "surface_form": row.declined_form or row.target_language_text or "",
                    "english_gloss": row.english_text or "",
                    "part_of_speech": row.part_of_speech or "",
                }
                for row in rows
            ],
        )

        if not annotate_language_dependencies(
            decomposition=decomposition, client=client, model=spec.model
        ):
            logger.warning(
                "Sentence %s: dependency annotation rejected for %s",
                sentence_id,
                language_code,
            )
            continue

        for row, word in zip(rows, decomposition.words):
            relation = word.get("ud_relation")
            head = word.get("ud_head_position")
            row.ud_relation = str(relation).strip() if relation is not None else None
            row.ud_head_position = (
                head if isinstance(head, int) and not isinstance(head, bool) else None
            )
        annotated_languages += 1

    session.flush()
    return f"annotate: {annotated_languages} language(s)"


def _run_link(session: Any, sentence_id: int, spec: SentenceImportSpec) -> str:
    outcome = link_sentence_words(session, sentence_id)
    return f"link: {outcome.summary()}"


def _run_stage(
    session: Any,
    sentence_id: int,
    spec: SentenceImportSpec,
    *,
    source: str,
    tags: Optional[str],
) -> str:
    """Stage whatever linking could not resolve.

    Re-runs the resolver rather than reusing the link stage's output, because
    the two stages can be reached independently -- a sentence whose linking was
    already complete still needs its unresolved words staged.
    """
    from wordfreq.tools.sentence_word_linker import ResolvedLemma

    unresolved: List[ResolvedLemma] = []
    for language_code in spec.decompose_languages:
        for word in unlinked_words(session, sentence_id, language_code):
            unresolved.append(
                ResolvedLemma(
                    position=word.position,
                    english_text=(word.english_text or "").strip(),
                    lemma=None,
                    method="unresolved",
                    confidence=0.0,
                    slot_name=word.part_of_speech,
                )
            )

    english = (
        session.query(SentenceTranslation)
        .filter_by(sentence_id=sentence_id, language_code="en")
        .first()
    )
    outcome = stage_unlinked_words(
        session,
        sentence_id,
        unresolved=unresolved,
        source=source,
        tags=tags,
        example_sentence=english.translation_text if english else None,
        notes=f"Staged by {TASK_TYPE} from sentence {sentence_id}",
    )
    return f"stage: {outcome.summary()}"


def _run_promote(
    session: Any,
    sentence_id: int,
    spec: SentenceImportSpec,
    *,
    data_source_config: DataSourceConfig,
    debug: bool,
) -> Tuple[str, int]:
    """Approve staged words if policy allows. Returns a summary and deferred count."""
    outcome = promote_sentence_pendings(
        session,
        sentence_id,
        policy=PromotionPolicy(auto_promote=spec.auto_promote),
        data_source_config=data_source_config,
        model=spec.model,
        debug=debug,
    )
    return (f"promote: {outcome.summary()}", len(outcome.deferred))


def _run_finalize(session: Any, sentence_id: int) -> str:
    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        return "finalize: sentence missing"
    level = calculate_minimum_level(session, sentence)
    session.flush()
    return f"finalize: minimum_level={level}"


def do_import_sentence(
    session: Any,
    sentence_id: int,
    target_languages: Optional[List[str]] = None,
    decompose_languages: Optional[List[str]] = None,
    annotate_dependencies: bool = False,
    auto_promote: bool = False,
    max_iterations: int = 3,
    iteration: int = 0,
    last_fingerprint: Optional[List[int]] = None,
    model: str = constants.DEFAULT_MODEL,
    source: Optional[str] = None,
    tags: Optional[str] = None,
    debug: bool = False,
    **_: Any,
) -> str:
    """Run one sentence as far through the import path as it can go.

    Args:
        session: Database session, owned by the worker.
        sentence_id: Sentence to import. Must already exist with at least one
            translation; creating it is ``sentences.import.document``'s job.
        target_languages: Languages to translate into.
        decompose_languages: Languages to break into words and link.
        annotate_dependencies: Run the Phase-4 Universal Dependencies pass.
        auto_promote: Let the workflow approve staged words into lemmas. Off by
            default; see :mod:`sentences.promotion`.
        max_iterations: Ceiling on promote/link re-entries.
        iteration: Which re-entry this is. Set by the workflow, not by callers.
        last_fingerprint: Progress at the end of the previous iteration. Set by
            the workflow, not by callers.
        model: LLM model for every stage that needs one.
        source: Provenance recorded on staged words.
        tags: Pre-serialized JSON tag array applied to staged words.
        debug: Verbose logging in the promotion path.

    Returns:
        A one-line summary of the stages that ran, stored as the task's result.
    """
    payload: Dict[str, Any] = {
        "target_languages": target_languages,
        "decompose_languages": decompose_languages,
        "annotate_dependencies": annotate_dependencies,
        "auto_promote": auto_promote,
        "max_iterations": max_iterations,
        "model": model,
    }
    spec = SentenceImportSpec.from_payload(payload)

    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        raise ValueError(f"Sentence {sentence_id} not found")

    config = DataSourceConfig(model=spec.model, debug=debug)
    client: Optional[UnifiedLLMClient] = None
    staging_source = source or f"{TASK_TYPE}/{sentence.guid or sentence_id}"

    steps: List[str] = []
    deferred_pendings = 0
    guard = 0
    # Each stage either completes or reports blocked, so the sequencer advances
    # every pass; the bound is a safety net against a stage that lies.
    max_steps = len(SentenceImportStage) + 2

    while guard < max_steps:
        guard += 1
        stage = next_incomplete_stage(session, sentence_id, spec=spec)
        if stage is None:
            break

        status = evaluate_stage(session, sentence_id, stage, spec=spec)
        if stage in _LLM_STAGES and client is None and stage is not SentenceImportStage.PROMOTE:
            client = UnifiedLLMClient.from_config(config)

        if stage is SentenceImportStage.INGEST:
            # Not runnable here: a sentence with no translation cannot be
            # invented. Reported and stopped rather than retried.
            reason = status.blocked_reason or "ingest incomplete"
            steps.append(f"ingest: blocked ({reason})")
            break

        if stage is SentenceImportStage.TRANSLATE:
            steps.append(_run_translate(session, sentence_id, spec, status))
        elif stage is SentenceImportStage.DECOMPOSE:
            assert client is not None
            steps.append(_run_decompose(session, sentence_id, spec, status, client))
        elif stage is SentenceImportStage.ANNOTATE:
            assert client is not None
            steps.append(_run_annotate(session, sentence_id, spec, client))
        elif stage is SentenceImportStage.LINK:
            steps.append(_run_link(session, sentence_id, spec))
        elif stage is SentenceImportStage.STAGE:
            steps.append(_run_stage(session, sentence_id, spec, source=staging_source, tags=tags))
        elif stage is SentenceImportStage.PROMOTE:
            summary, deferred_pendings = _run_promote(
                session,
                sentence_id,
                spec,
                data_source_config=config,
                debug=debug,
            )
            steps.append(summary)
            session.commit()
            break
        elif stage is SentenceImportStage.FINALIZE:
            steps.append(_run_finalize(session, sentence_id))

        session.commit()

    fingerprint = progress_fingerprint(session, sentence_id)
    remaining = next_incomplete_stage(session, sentence_id, spec=spec)

    if remaining is None:
        steps.append("complete")
    elif deferred_pendings:
        steps.append(f"awaiting {deferred_pendings} approval(s)")
    elif last_fingerprint is not None and list(fingerprint) == list(last_fingerprint):
        # The previous iteration changed nothing, so another will not either.
        steps.append(f"stopped at {remaining.value}: no progress")
    elif iteration + 1 >= spec.max_iterations:
        steps.append(f"stopped at {remaining.value}: iteration cap {spec.max_iterations}")
    else:
        enqueue_task(
            session,
            task_type=TASK_TYPE,
            target_type="sentence",
            target_id=sentence_id,
            payload={
                "sentence_id": sentence_id,
                "target_languages": list(spec.target_languages),
                "decompose_languages": list(spec.decompose_languages),
                "annotate_dependencies": spec.annotate_dependencies,
                "auto_promote": spec.auto_promote,
                "max_iterations": spec.max_iterations,
                "iteration": iteration + 1,
                "last_fingerprint": list(fingerprint),
                "model": spec.model,
                "source": source,
                "tags": tags,
            },
            dedup_key=f"{TASK_TYPE}:{sentence_id}:{iteration + 1}",
        )
        steps.append(f"requeued at {remaining.value} (iteration {iteration + 1})")
        session.commit()

    session.commit()
    return f"sentence {sentence_id}: " + "; ".join(steps)


handle_sentences_import = workqueue_payload_handler()(do_import_sentence)
"""Workqueue entry point for ``sentences.import``."""
