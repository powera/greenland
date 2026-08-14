"""Workqueue package for background task processing.

This package contains all workqueue-related functionality:
- task_queue: Task status, types, and queue operations (enqueue, claim, etc.)
- pipeline_order: Pipeline ordering for dependent tasks
- registry: Handler registry (TASK_HANDLERS) and custom handlers
- worker: Background worker daemon
- stats: Per-status task counts for reporting
- tools: Common utilities for handler implementations
- handlers/: Individual handler modules by agent name
"""

# Re-export commonly used items for convenience
from workqueue.task_queue import (
    TaskStatus,
    TaskType,
    EnqueueResult,
    EnqueueSummary,
    TaskRequest,
    enqueue_task,
    enqueue_tasks,
    claim_next_task,
    mark_task_complete,
    mark_task_failed,
    get_tasks_for_target,
    get_active_task,
    has_earlier_pending_task,
)
from workqueue.pipeline_order import (
    TASK_PIPELINE_ORDER,
    get_pipeline_step,
    has_earlier_step,
)
from workqueue.registry import TASK_HANDLERS
from workqueue.stats import TaskCounts, get_task_type_counts, has_queued_work
from workqueue.tools import (
    build_default_config,
    get_lemma_or_raise,
    extract_payload_param,
    commit_or_raise,
    workqueue_payload_handler,
)

__all__ = [
    # task_queue
    "TaskStatus",
    "TaskType",
    "EnqueueResult",
    "EnqueueSummary",
    "TaskRequest",
    "enqueue_task",
    "enqueue_tasks",
    "claim_next_task",
    "mark_task_complete",
    "mark_task_failed",
    "get_tasks_for_target",
    "get_active_task",
    "has_earlier_pending_task",
    # pipeline_order
    "TASK_PIPELINE_ORDER",
    "get_pipeline_step",
    "has_earlier_step",
    # registry
    "TASK_HANDLERS",
    # stats
    "TaskCounts",
    "get_task_type_counts",
    "has_queued_work",
    # tools
    "build_default_config",
    "get_lemma_or_raise",
    "extract_payload_param",
    "commit_or_raise",
    "workqueue_payload_handler",
]
