"""Stage model for the sentence import path.

Importing a sentence is a fixed sequence of tasks: translate it, decompose it
into words, pair those words to lemmas, stage the words that have no lemma, and
get those lemmas into the database. This module answers one question -- "what
still needs doing for this sentence?" -- and answers it by *reading the data*
rather than by consulting a stored status column.

Deriving the stage rather than storing it is deliberate. Four components write
sentence rows (``agents.genys``, the conversation scene handler,
``workqueue.handlers.sentences.translation``, and ``agents.buivolas``), none of
which knows a workflow exists. A stored column would be stale the moment any of
them ran, and would need a backfill for every sentence already in the database.
A derived stage is correct for a sentence no matter which path created it.

The cost of deriving is that "never attempted" and "attempted, and legitimately
produced nothing" look identical. Two things cover that gap:

* Stages report *blocked* separately from *incomplete*. Phase 3 skips by design
  when fewer than :data:`PHASE3_MIN_LANGUAGES` translations exist, and a stage
  that cannot proceed must not stall the machine.
* :func:`import_attempt_count` reads the existing ``BarsukasTask`` rows for the
  sentence, so attempt history costs no new schema.

If task rows are ever pruned aggressively enough that the attempt history stops
being usable, the escape hatch is a ``sentence_import_attempts`` table keyed on
``(sentence_id, stage)``. That is deliberately not built yet.

Everything here is a pure read: no LLM client, no queue imports, no commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from langtools.grammatical_words import is_function_word, is_grammatical_word
from sentences.translate_and_decompose import DEFAULT_MODEL, PHASE3_MIN_LANGUAGES
from storage.models.imports import PendingImport
from storage.models.schema import (
    Sentence,
    SentenceTranslation,
    SentenceWord,
    SentenceWordHint,
)

# Parts of speech that map onto a lemma's ``pos_type``. A word whose POS is not
# in this map can still be staged, but with no pos_type to filter duplicates by.
PART_OF_SPEECH_MAP: Dict[str, str] = {
    "noun": "noun",
    "verb": "verb",
    "adjective": "adjective",
    "adverb": "adverb",
}

# Parts of speech that never become lemmas of their own. This set and
# ``is_function_word`` together define "should this word carry a lemma_id",
# which is the predicate stage LINK completes against and the predicate staging
# skips on. They must stay in agreement: if the two disagree, a word can be
# neither linkable nor skippable and stage LINK never goes true.
SKIPPED_PARTS_OF_SPEECH: Set[str] = {
    "article",
    "preposition",
    "conjunction",
    "determiner",
    "particle",
}


class SentenceImportStage(str, Enum):
    """One step of the import path, in execution order.

    Values are lowercase words so they read directly in a task result message
    and can be grepped out of logs.
    """

    INGEST = "ingest"
    TRANSLATE = "translate"
    DECOMPOSE = "decompose"
    ANNOTATE = "annotate"
    LINK = "link"
    STAGE = "stage"
    PROMOTE = "promote"
    IDIOMS = "idioms"
    FINALIZE = "finalize"


# Execution order. IDIOMS is a placeholder that always reports complete; it is
# present so that adding idiom detection later does not renumber the sequence
# or change any stored value.
STAGE_ORDER: Tuple[SentenceImportStage, ...] = (
    SentenceImportStage.INGEST,
    SentenceImportStage.TRANSLATE,
    SentenceImportStage.DECOMPOSE,
    SentenceImportStage.ANNOTATE,
    SentenceImportStage.LINK,
    SentenceImportStage.STAGE,
    SentenceImportStage.PROMOTE,
    SentenceImportStage.IDIOMS,
    SentenceImportStage.FINALIZE,
)

DEFAULT_TARGET_LANGUAGES: Tuple[str, ...] = ("en", "es", "fr", "zh", "lt")
DEFAULT_DECOMPOSE_LANGUAGES: Tuple[str, ...] = ("en",)


@dataclass(frozen=True)
class SentenceImportSpec:
    """Configuration for one import run.

    Held separately from the stage predicates so that the predicates never read
    configuration themselves -- what "complete" means for TRANSLATE depends
    entirely on which languages were asked for.
    """

    target_languages: Tuple[str, ...] = DEFAULT_TARGET_LANGUAGES
    decompose_languages: Tuple[str, ...] = DEFAULT_DECOMPOSE_LANGUAGES
    annotate_dependencies: bool = False
    auto_promote: bool = False
    max_iterations: int = 3
    model: str = DEFAULT_MODEL

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "SentenceImportSpec":
        """Build a spec from a workqueue task payload, applying defaults."""

        def _languages(key: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
            raw = payload.get(key)
            if not raw:
                return default
            if isinstance(raw, str):
                items = [part.strip() for part in raw.split(",")]
            else:
                items = [str(part).strip() for part in raw]
            cleaned = tuple(item.lower() for item in items if item)
            return cleaned or default

        max_iterations_raw = payload.get("max_iterations")
        try:
            max_iterations = int(max_iterations_raw) if max_iterations_raw is not None else 3
        except (TypeError, ValueError):
            max_iterations = 3

        return cls(
            target_languages=_languages("target_languages", DEFAULT_TARGET_LANGUAGES),
            decompose_languages=_languages("decompose_languages", DEFAULT_DECOMPOSE_LANGUAGES),
            annotate_dependencies=bool(payload.get("annotate_dependencies", False)),
            auto_promote=bool(payload.get("auto_promote", False)),
            max_iterations=max(1, max_iterations),
            model=str(payload.get("model") or DEFAULT_MODEL),
        )


@dataclass(frozen=True)
class StageStatus:
    """The verdict for one stage.

    ``complete`` and ``blocked_reason`` are independent: a blocked stage reports
    ``complete=False`` with a reason, and the sequencer treats it as done-for-
    ordering so the machine moves past it rather than retrying forever.
    """

    stage: SentenceImportStage
    complete: bool
    blocked_reason: Optional[str] = None
    detail: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.detail is None:
            object.__setattr__(self, "detail", {})

    @property
    def settled(self) -> bool:
        """True when this stage needs no further work, complete or blocked."""
        return self.complete or self.blocked_reason is not None


# ---------------------------------------------------------------------- #
# Word classification                                                     #
# ---------------------------------------------------------------------- #


def should_carry_lemma(word: SentenceWord, language_code: str = "en") -> bool:
    """True when this word is expected to resolve to a lemma.

    Grammatical and function words never get lemmas, so demanding one for them
    would leave stage LINK permanently incomplete.
    """
    text = (word.english_text or "").strip()
    if not text:
        return False

    part_of_speech = (word.part_of_speech or "").strip().lower()
    if part_of_speech in SKIPPED_PARTS_OF_SPEECH:
        return False

    if is_grammatical_word(text, "en"):
        return False

    surface = (word.declined_form or word.target_language_text or "").strip()
    if surface and is_function_word(surface, language_code):
        return False

    return True


def linkable_words(
    session: Session, sentence_id: int, language_code: str = "en"
) -> List[SentenceWord]:
    """Words in one language that are expected to carry a lemma."""
    rows = (
        session.query(SentenceWord)
        .filter(
            SentenceWord.sentence_id == sentence_id,
            SentenceWord.language_code == language_code,
        )
        .order_by(SentenceWord.position)
        .all()
    )
    return [word for word in rows if should_carry_lemma(word, language_code)]


def unlinked_words(
    session: Session, sentence_id: int, language_code: str = "en"
) -> List[SentenceWord]:
    """Linkable words that still have neither a lemma nor a name attached."""
    return [
        word
        for word in linkable_words(session, sentence_id, language_code)
        if word.lemma_id is None and word.name_id is None
    ]


# ---------------------------------------------------------------------- #
# Stage predicates                                                        #
# ---------------------------------------------------------------------- #


def _translated_languages(session: Session, sentence_id: int) -> Set[str]:
    rows = (
        session.query(SentenceTranslation.language_code)
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .all()
    )
    return {str(row[0]).strip().lower() for row in rows if row[0]}


def _decomposed_languages(session: Session, sentence_id: int) -> Set[str]:
    rows = (
        session.query(SentenceWord.language_code)
        .filter(SentenceWord.sentence_id == sentence_id)
        .distinct()
        .all()
    )
    return {str(row[0]).strip().lower() for row in rows if row[0]}


def _evaluate_ingest(session: Session, sentence_id: int) -> StageStatus:
    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        return StageStatus(
            stage=SentenceImportStage.INGEST,
            complete=False,
            blocked_reason=f"sentence {sentence_id} does not exist",
        )
    translated = _translated_languages(session, sentence_id)
    if not translated:
        return StageStatus(
            stage=SentenceImportStage.INGEST,
            complete=False,
            blocked_reason="sentence has no translation to work from",
        )
    return StageStatus(
        stage=SentenceImportStage.INGEST,
        complete=True,
        detail={"languages": sorted(translated)},
    )


def _evaluate_translate(
    session: Session, sentence_id: int, spec: SentenceImportSpec
) -> StageStatus:
    have = _translated_languages(session, sentence_id)
    missing = [lang for lang in spec.target_languages if lang not in have]
    return StageStatus(
        stage=SentenceImportStage.TRANSLATE,
        complete=not missing,
        detail={"missing_languages": missing, "have": sorted(have)},
    )


def _evaluate_decompose(
    session: Session, sentence_id: int, spec: SentenceImportSpec
) -> StageStatus:
    have = _decomposed_languages(session, sentence_id)
    missing = [lang for lang in spec.decompose_languages if lang not in have]
    if not missing:
        return StageStatus(stage=SentenceImportStage.DECOMPOSE, complete=True)

    available = len(_translated_languages(session, sentence_id))
    if available < PHASE3_MIN_LANGUAGES:
        return StageStatus(
            stage=SentenceImportStage.DECOMPOSE,
            complete=False,
            blocked_reason=(
                f"decomposition needs {PHASE3_MIN_LANGUAGES} languages, have {available}"
            ),
            detail={"missing_languages": missing, "available_languages": available},
        )
    return StageStatus(
        stage=SentenceImportStage.DECOMPOSE,
        complete=False,
        detail={"missing_languages": missing},
    )


def _evaluate_annotate(session: Session, sentence_id: int, spec: SentenceImportSpec) -> StageStatus:
    if not spec.annotate_dependencies:
        return StageStatus(
            stage=SentenceImportStage.ANNOTATE,
            complete=True,
            detail={"requested": False},
        )

    pending = (
        session.query(func.count(SentenceWord.id))
        .filter(
            SentenceWord.sentence_id == sentence_id,
            SentenceWord.language_code.in_(list(spec.decompose_languages)),
            SentenceWord.ud_relation.is_(None),
        )
        .scalar()
        or 0
    )
    return StageStatus(
        stage=SentenceImportStage.ANNOTATE,
        complete=pending == 0,
        detail={"unannotated": int(pending)},
    )


def _evaluate_link(session: Session, sentence_id: int, spec: SentenceImportSpec) -> StageStatus:
    outstanding: Dict[str, int] = {}
    for language_code in spec.decompose_languages:
        count = len(unlinked_words(session, sentence_id, language_code))
        if count:
            outstanding[language_code] = count
    return StageStatus(
        stage=SentenceImportStage.LINK,
        complete=not outstanding,
        detail={"unlinked": outstanding},
    )


def _evaluate_stage(session: Session, sentence_id: int, spec: SentenceImportSpec) -> StageStatus:
    """Complete when every word LINK could not resolve has been staged.

    A word is "staged" when a hint row for the sentence carries its
    ``pending_import_id``. Matching is by lowercased English text rather than by
    position, because hint positions are slot-shaped while sentence-word
    positions are token-shaped.
    """
    staged_texts = {
        str(row[0]).strip().lower()
        for row in session.query(SentenceWordHint.english_text)
        .filter(
            SentenceWordHint.sentence_id == sentence_id,
            SentenceWordHint.pending_import_id.isnot(None),
        )
        .all()
        if row[0]
    }

    unstaged: List[str] = []
    for language_code in spec.decompose_languages:
        for word in unlinked_words(session, sentence_id, language_code):
            text = (word.english_text or "").strip().lower()
            if text and text not in staged_texts:
                unstaged.append(text)

    return StageStatus(
        stage=SentenceImportStage.STAGE,
        complete=not unstaged,
        detail={"unstaged": sorted(set(unstaged))},
    )


def _outstanding_pending_import_ids(session: Session, sentence_id: int) -> List[int]:
    """Pending imports this sentence is waiting on that still exist.

    ``approve_pending_import`` deletes the row on success, so a hint pointing at
    a row that is gone is a promotion that already happened.
    """
    rows = (
        session.query(SentenceWordHint.pending_import_id)
        .filter(
            SentenceWordHint.sentence_id == sentence_id,
            SentenceWordHint.pending_import_id.isnot(None),
        )
        .all()
    )
    candidate_ids = {int(row[0]) for row in rows if row[0] is not None}
    if not candidate_ids:
        return []

    alive = {
        int(row[0])
        for row in session.query(PendingImport.id)
        .filter(PendingImport.id.in_(sorted(candidate_ids)))
        .all()
    }
    return sorted(alive)


def _evaluate_promote(session: Session, sentence_id: int) -> StageStatus:
    outstanding = _outstanding_pending_import_ids(session, sentence_id)
    return StageStatus(
        stage=SentenceImportStage.PROMOTE,
        complete=not outstanding,
        detail={"pending_import_ids": outstanding},
    )


def _evaluate_finalize(session: Session, sentence_id: int) -> StageStatus:
    """Complete when the stored level agrees with the currently linked lemmas.

    ``calculate_minimum_level`` legitimately yields NULL for a sentence whose
    linked lemmas have no difficulty set, so "is not NULL" would never settle.
    Comparing against a recomputed value settles in both cases and re-opens the
    stage whenever linking changes the answer.
    """
    from storage.crud.sentence import calculate_minimum_level

    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        return StageStatus(
            stage=SentenceImportStage.FINALIZE,
            complete=False,
            blocked_reason=f"sentence {sentence_id} does not exist",
        )

    stored = sentence.minimum_level
    expected = calculate_minimum_level(session, sentence)
    # calculate_minimum_level assigns as a side effect; restore so a pure read
    # never mutates. The orchestrator calls it again to make the change stick.
    sentence.minimum_level = stored
    return StageStatus(
        stage=SentenceImportStage.FINALIZE,
        complete=stored == expected,
        detail={"stored_level": stored, "expected_level": expected},
    )


def evaluate_stage(
    session: Session,
    sentence_id: int,
    stage: SentenceImportStage,
    *,
    spec: SentenceImportSpec,
) -> StageStatus:
    """Return the verdict for one stage of one sentence."""
    if stage is SentenceImportStage.INGEST:
        return _evaluate_ingest(session, sentence_id)
    if stage is SentenceImportStage.TRANSLATE:
        return _evaluate_translate(session, sentence_id, spec)
    if stage is SentenceImportStage.DECOMPOSE:
        return _evaluate_decompose(session, sentence_id, spec)
    if stage is SentenceImportStage.ANNOTATE:
        return _evaluate_annotate(session, sentence_id, spec)
    if stage is SentenceImportStage.LINK:
        return _evaluate_link(session, sentence_id, spec)
    if stage is SentenceImportStage.STAGE:
        return _evaluate_stage(session, sentence_id, spec)
    if stage is SentenceImportStage.PROMOTE:
        return _evaluate_promote(session, sentence_id)
    if stage is SentenceImportStage.IDIOMS:
        # Deferred: needs a sentence-to-idiom link and a multi-word
        # PendingImport, neither of which exists yet.
        return StageStatus(
            stage=SentenceImportStage.IDIOMS,
            complete=True,
            detail={"deferred": True},
        )
    return _evaluate_finalize(session, sentence_id)


def evaluate_all(
    session: Session, sentence_id: int, *, spec: SentenceImportSpec
) -> List[StageStatus]:
    """Return every stage's verdict, in execution order."""
    return [evaluate_stage(session, sentence_id, stage, spec=spec) for stage in STAGE_ORDER]


def next_incomplete_stage(
    session: Session, sentence_id: int, *, spec: SentenceImportSpec
) -> Optional[SentenceImportStage]:
    """Return the first stage needing work, or None when nothing does.

    A blocked stage counts as settled: the machine steps past it instead of
    sitting on a stage that cannot proceed.
    """
    for stage in STAGE_ORDER:
        status = evaluate_stage(session, sentence_id, stage, spec=spec)
        if not status.settled:
            return stage
    return None


# ---------------------------------------------------------------------- #
# Progress and history                                                    #
# ---------------------------------------------------------------------- #


def progress_fingerprint(session: Session, sentence_id: int) -> Tuple[int, int, int, int]:
    """A cheap summary of how far the sentence has come.

    The orchestrator carries this across a re-entry. When an iteration ends with
    the fingerprint it started with, nothing changed and another iteration will
    change nothing either -- that is what makes the promote/link loop terminate
    regardless of why a stage failed to make progress.
    """
    linked = (
        session.query(func.count(SentenceWord.id))
        .filter(
            SentenceWord.sentence_id == sentence_id,
            SentenceWord.lemma_id.isnot(None),
        )
        .scalar()
        or 0
    )
    staged = (
        session.query(func.count(SentenceWordHint.id))
        .filter(
            SentenceWordHint.sentence_id == sentence_id,
            SentenceWordHint.pending_import_id.isnot(None),
        )
        .scalar()
        or 0
    )
    translations = (
        session.query(func.count(SentenceTranslation.id))
        .filter(SentenceTranslation.sentence_id == sentence_id)
        .scalar()
        or 0
    )
    words = (
        session.query(func.count(SentenceWord.id))
        .filter(SentenceWord.sentence_id == sentence_id)
        .scalar()
        or 0
    )
    return (int(linked), int(staged), int(translations), int(words))


def import_attempt_count(session: Session, sentence_id: int, task_type: str) -> int:
    """How many import tasks have already been recorded for this sentence.

    Reads the existing task table rather than a status column, so attempt
    history costs no new schema. Returns 0 if the task table is unavailable.
    """
    from storage.models.schema import BarsukasTask

    count = (
        session.query(func.count(BarsukasTask.id))
        .filter(
            BarsukasTask.task_type == task_type,
            BarsukasTask.target_type == "sentence",
            BarsukasTask.target_id == sentence_id,
        )
        .scalar()
        or 0
    )
    return int(count)
