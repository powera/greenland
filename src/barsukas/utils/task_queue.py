"""Lightweight task queue for Barsukas background work.

This module stores queue metadata in the shared SQLite database using the
`BarsukasTask` model. It keeps the web UI responsive by deferring expensive LLM
calls to a separate worker process while preventing duplicate in-flight tasks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from wordfreq.storage.models.schema import BarsukasTask

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


@dataclass
class EnqueueResult:
    task: BarsukasTask
    created: bool


def _serialize_payload(payload: Optional[Dict]) -> Optional[str]:
    if payload is None:
        return None
    return json.dumps(payload)


def enqueue_task(
    session,
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


def claim_next_task(session) -> Optional[BarsukasTask]:
    """Atomically claim the next pending task."""
    task = (
        session.query(BarsukasTask)
        .filter(BarsukasTask.status == TaskStatus.PENDING)
        .order_by(BarsukasTask.created_at.asc())
        .first()
    )
    if not task:
        return None

    task.status = TaskStatus.RUNNING
    task.started_at = datetime.utcnow()
    session.flush()
    return task


def mark_task_complete(session, task: BarsukasTask, message: str) -> None:
    task.status = TaskStatus.COMPLETED
    task.result_message = message
    task.finished_at = datetime.utcnow()
    session.flush()


def mark_task_failed(
    session, task: BarsukasTask, message: str, error_detail: Optional[str] = None
) -> None:
    task.status = TaskStatus.FAILED
    task.result_message = message
    task.error_detail = error_detail
    task.finished_at = datetime.utcnow()
    session.flush()


def get_tasks_for_target(session, target_type: str, target_id: int, limit: int = 10):
    return (
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


def get_active_task(session, dedup_key: str) -> Optional[BarsukasTask]:
    return (
        session.query(BarsukasTask)
        .filter(
            BarsukasTask.dedup_key == dedup_key,
            BarsukasTask.status.in_(TaskStatus.ACTIVE),
        )
        .order_by(BarsukasTask.created_at.desc())
        .first()
    )
