"""Queue statistics shared by the agent CLIs and the Barsukas UI.

Counting is generic: callers name the task types they care about and get one
row of per-status counts back. Formatting the rows is the caller's business.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Sequence, TypedDict

from sqlalchemy import func

from storage.models.schema import BarsukasTask
from workqueue.task_queue import TaskStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

__all__ = ["TaskCounts", "get_task_type_counts", "has_queued_work"]


class TaskCounts(TypedDict):
    """Per-status task counts for a single task type."""

    pending: int
    running: int
    completed: int
    failed: int


# Statuses reported for every task type, in display order.
_REPORTED_STATUSES = (
    TaskStatus.PENDING,
    TaskStatus.RUNNING,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
)


def get_task_type_counts(session: "Session", task_types: Sequence[str]) -> Dict[str, TaskCounts]:
    """Count tasks per status for each requested task type.

    Args:
        session: Database session.
        task_types: The task types to report on. Types with no rows at all are
            still present in the result, with zero counts.

    Returns:
        A ``task_type -> TaskCounts`` mapping, keyed in the requested order.
    """
    stats: Dict[str, TaskCounts] = {
        task_type: TaskCounts(pending=0, running=0, completed=0, failed=0)
        for task_type in task_types
    }
    if not stats:
        return stats

    rows = (
        session.query(BarsukasTask.task_type, BarsukasTask.status, func.count(BarsukasTask.id))
        .filter(BarsukasTask.task_type.in_(list(stats)))
        .filter(BarsukasTask.status.in_(list(_REPORTED_STATUSES)))
        .group_by(BarsukasTask.task_type, BarsukasTask.status)
        .all()
    )
    for task_type, status, count in rows:
        stats[task_type][status] = count  # type: ignore[literal-required]
    return stats


def has_queued_work(counts: TaskCounts) -> bool:
    """True when a task type has any task in a reported status."""
    return sum(counts[status] for status in _REPORTED_STATUSES) > 0  # type: ignore[literal-required]
