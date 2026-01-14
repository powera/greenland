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
from typing import TYPE_CHECKING, Dict, List, Optional

from wordfreq.storage.models.schema import BarsukasTask

from barsukas.utils.pipeline_order import get_pipeline_step

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
    ADD_MISSING_TRANSLATIONS = "add_missing_translations"
    GENERATE_PRONUNCIATIONS = "generate_pronunciations"
    GENERATE_FORMS = "generate_forms"
    GENERATE_SYNONYMS = "generate_synonyms"
    TRANSLATE_SENTENCE = "translate_sentence"
    GENERATE_AUDIO = "generate_audio"
    GENERATE_GRAMMAR_FACT = "generate_grammar_fact"


@dataclass
class EnqueueResult:
    task: BarsukasTask
    created: bool


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
