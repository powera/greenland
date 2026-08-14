"""Lightweight task queue for Barsukas background work.

This module stores queue metadata in the shared SQLite database using the
`BarsukasTask` model. It keeps the web UI responsive by deferring expensive LLM
calls to a separate worker process while preventing duplicate in-flight tasks.

Tasks for the same lemma are executed in pipeline order to ensure dependencies
are satisfied (e.g., translations must complete before pronunciations).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, TypedDict

from storage.models.schema import BarsukasTask

from workqueue.pipeline_order import get_pipeline_step

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    ACTIVE = {PENDING, RUNNING}


class TaskType:
    WORDS_TRANSLATIONS = "words.translations"
    WORDS_TRANSLATIONS_REGENERATE = "words.translations.regenerate"
    WORDS_TRANSLATIONS_VERIFY = "words.translations.verify"
    WORDS_PRONUNCIATIONS = "words.pronunciations"
    WORDS_FORMS = "words.forms"
    WORDS_SYNONYMS = "words.synonyms"
    WORDS_EMBEDDINGS = "words.embeddings"
    WORDS_GRAMMAR_FACTS = "words.grammar_facts"
    CONVERSATIONS_GENERATE = "conversations.generate"
    CONVERSATIONS_DEFINITIONS = "conversations.definitions.generate"
    CONVERSATIONS_SCENE_GENERATE = "conversations.scene.generate"
    SENTENCES_IMPORT = "sentences.import"
    SENTENCES_IMPORT_DOCUMENT = "sentences.import.document"
    SENTENCES_PATTERNS_GENERATE = "sentences.patterns.generate"
    SENTENCES_EXAMPLES_GENERATE = "sentences.examples.generate"
    SENTENCES_TRANSLATE = "sentences.translate"
    SENTENCES_TRANSLATE_SIMPLE = "sentences.translate.simple"
    SENTENCES_TRANSLATIONS_VERIFY = "sentences.translations.verify"
    SENTENCES_LINKS_VERIFY = "sentences.links.verify"
    SENTENCES_TRANSLATE_BATCH_SUBMIT = "sentences.translate.batch_submit"
    SENTENCES_BATCH_TRANSLATE_SUBMIT = "sentences.batch.translate.submit"
    SENTENCES_BATCH_DECOMPOSE_SUBMIT = "sentences.batch.decompose.submit"
    AUDIO_GENERATE_LEMMA = "audio.generate.lemma"
    AUDIO_GENERATE_SENTENCE = "audio.generate.sentence"
    WIREWORD_EXPORT_DIRECTORY = "wireword.export.directory"

    # Legacy aliases retained for compatibility during migration
    ADD_MISSING_TRANSLATIONS = WORDS_TRANSLATIONS
    GENERATE_PRONUNCIATIONS = WORDS_PRONUNCIATIONS
    GENERATE_FORMS = WORDS_FORMS
    GENERATE_SYNONYMS = WORDS_SYNONYMS
    GENERATE_GRAMMAR_FACT = WORDS_GRAMMAR_FACTS
    TRANSLATE_SENTENCE = SENTENCES_TRANSLATE
    GENERATE_AUDIO = AUDIO_GENERATE_LEMMA
    GENERATE_SENTENCE_AUDIO = AUDIO_GENERATE_SENTENCE


@dataclass
class EnqueueResult:
    task: BarsukasTask
    created: bool


@dataclass(frozen=True)
class TaskRequest:
    """One task an agent wants queued, before dedup is considered.

    Agents describe *what* to enqueue; :func:`enqueue_tasks` owns the mechanics
    (dedup lookups, dry-run accounting, the commit).

    Attributes:
        task_type: A :class:`TaskType` value.
        target_type: The kind of row the task acts on (e.g. ``"lemma"``).
        target_id: The row's primary key.
        payload: JSON-serializable task payload.
        dedup_key: Canonical dedup key, normally ``f"{task_type}:{...}"``.
        legacy_dedup_key: Dedup key an older release used for the same work.
            An active task under that key also suppresses this request, so a
            queue drained by an older worker is not duplicated.
    """

    task_type: str
    target_type: Optional[str]
    target_id: Optional[int]
    payload: Optional[Dict] = None
    dedup_key: Optional[str] = None
    legacy_dedup_key: Optional[str] = None


class EnqueueSummary(TypedDict):
    """Counts returned by :func:`enqueue_tasks`."""

    enqueued: int
    skipped: int
    dry_run: bool


def enqueue_tasks(
    session: "Session",
    requests: Iterable[TaskRequest],
    *,
    dry_run: bool = False,
) -> EnqueueSummary:
    """Enqueue a batch of task requests, skipping ones already active.

    Args:
        session: Database session. Committed once at the end unless dry-running.
        requests: The tasks to queue.
        dry_run: If True, count what would be queued and write nothing.

    Returns:
        An :class:`EnqueueSummary` with ``enqueued``/``skipped`` counts.
    """
    enqueued = 0
    skipped = 0

    for request in requests:
        if dry_run:
            enqueued += 1
            continue
        if (
            request.legacy_dedup_key
            and get_active_task(session, request.legacy_dedup_key) is not None
        ):
            skipped += 1
            continue
        result = enqueue_task(
            session,
            task_type=request.task_type,
            target_type=request.target_type,
            target_id=request.target_id,
            payload=request.payload,
            dedup_key=request.dedup_key,
        )
        if result.created:
            enqueued += 1
        else:
            skipped += 1

    if not dry_run:
        session.commit()

    return EnqueueSummary(enqueued=enqueued, skipped=skipped, dry_run=dry_run)


def _serialize_payload(payload: Optional[Dict]) -> Optional[str]:
    if payload is None:
        return None
    return json.dumps(payload)


def enqueue_task(
    session: "Session",
    *,
    task_type: str,
    target_type: Optional[str],
    target_id: Optional[int],
    payload: Optional[Dict] = None,
    dedup_key: Optional[str] = None,
) -> EnqueueResult:
    """Create a queue entry unless an active duplicate already exists."""

    if dedup_key:
        existing = (
            session.query(BarsukasTask)
            .filter(
                BarsukasTask.dedup_key == dedup_key,
                BarsukasTask.status.in_(TaskStatus.ACTIVE),
            )
            .order_by(BarsukasTask.created_at.asc())
            .first()
        )
        if existing:
            logger.debug("Task with dedup_key %s already active (id=%s)", dedup_key, existing.id)
            return EnqueueResult(task=existing, created=False)

    task = BarsukasTask(
        task_type=task_type,
        target_type=target_type,
        target_id=target_id,
        dedup_key=dedup_key,
        status=TaskStatus.PENDING,
        payload=_serialize_payload(payload),
    )
    session.add(task)
    session.flush()
    return EnqueueResult(task=task, created=True)


def has_earlier_pending_task(session: "Session", task: BarsukasTask) -> bool:
    """Check if there's an earlier pipeline task pending for the same lemma.

    Returns True if this task should wait for an earlier task to complete.
    Only applies to lemma-targeted tasks that are part of the pipeline.
    """
    # Only check lemma tasks that are in the pipeline
    if task.target_type != "lemma" or task.target_id is None:
        return False

    current_step = get_pipeline_step(task.task_type)
    if current_step is None:
        return False

    # Check for any pending tasks on the same lemma with earlier pipeline steps
    earlier_tasks = (
        session.query(BarsukasTask)
        .filter(
            BarsukasTask.target_type == "lemma",
            BarsukasTask.target_id == task.target_id,
            BarsukasTask.status == TaskStatus.PENDING,
            BarsukasTask.id != task.id,  # Exclude current task
        )
        .all()
    )

    for earlier_task in earlier_tasks:
        earlier_step = get_pipeline_step(earlier_task.task_type)
        if earlier_step is not None and earlier_step < current_step:
            logger.debug(
                "Task %s (step %s) blocked by earlier task %s (step %s) for lemma %s",
                task.id,
                current_step,
                earlier_task.id,
                earlier_step,
                task.target_id,
            )
            return True

    return False


def claim_next_task(session: "Session") -> Optional[BarsukasTask]:
    """Atomically claim the next pending task, respecting pipeline order.

    For lemma tasks, skips tasks that have earlier pipeline steps pending
    to ensure proper execution order (e.g., translations before pronunciations).
    """
    # Get all pending tasks ordered by creation time
    pending_tasks = (
        session.query(BarsukasTask)
        .filter(BarsukasTask.status == TaskStatus.PENDING)
        .order_by(BarsukasTask.created_at.asc())
        .all()
    )

    # Find the first task that doesn't have earlier pending dependencies
    for task in pending_tasks:
        if not has_earlier_pending_task(session, task):
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            session.flush()
            return task  # type: ignore[no-any-return]

    # All pending tasks are blocked by earlier dependencies
    return None


def mark_task_complete(session: "Session", task: BarsukasTask, message: str) -> None:
    task.status = TaskStatus.COMPLETED
    task.result_message = message
    task.finished_at = datetime.utcnow()
    session.flush()


def mark_task_failed(
    session: "Session", task: BarsukasTask, message: str, error_detail: Optional[str] = None
) -> None:
    task.status = TaskStatus.FAILED
    task.result_message = message
    task.error_detail = error_detail
    task.finished_at = datetime.utcnow()
    session.flush()


def get_tasks_for_target(
    session: "Session", target_type: str, target_id: int, limit: int = 10
) -> List[BarsukasTask]:
    return (  # type: ignore[no-any-return]
        session.query(BarsukasTask)
        .filter(
            BarsukasTask.target_type == target_type,
            BarsukasTask.target_id == target_id,
            BarsukasTask.status.in_(
                [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED]
            ),
        )
        .order_by(BarsukasTask.created_at.desc())
        .limit(limit)
        .all()
    )


def get_active_task(session: "Session", dedup_key: str) -> Optional[BarsukasTask]:
    return (  # type: ignore[no-any-return]
        session.query(BarsukasTask)
        .filter(
            BarsukasTask.dedup_key == dedup_key,
            BarsukasTask.status.in_(TaskStatus.ACTIVE),
        )
        .order_by(BarsukasTask.created_at.desc())
        .first()
    )
