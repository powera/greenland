"""Generic work queue for agent batch processing.

This module provides a reusable work queue for agents that need to defer or batch
work items (typically LLM calls). Unlike the OpenAI-specific batch queue, this is
generic and works with any agent operation.

Usage:
    # Enqueue work
    work_item = enqueue_work(
        session,
        agent_name="lape",
        operation_type="generate_measure_words",
        lemma_id=lemma.id,
        language_code="zh",
        metadata={"fact_type": "measure_words"},
    )

    # Process work
    work_item = claim_next_work(session, agent_name="lape")
    if work_item:
        # ... do work ...
        mark_work_completed(session, work_item, "Success")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from wordfreq.storage.models.schema import AgentWorkQueue

logger = logging.getLogger(__name__)


class WorkStatus:
    """Work item status constants."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    ACTIVE = {PENDING, PROCESSING}


@dataclass
class EnqueueResult:
    """Result of enqueuing a work item."""

    work_item: AgentWorkQueue
    created: bool


def _serialize_metadata(metadata: Optional[Dict]) -> Optional[str]:
    """Serialize metadata dict to JSON string."""
    if metadata is None:
        return None
    return json.dumps(metadata)


def _deserialize_metadata(metadata_str: Optional[str]) -> Optional[Dict]:
    """Deserialize metadata JSON string to dict."""
    if metadata_str is None:
        return None
    try:
        return json.loads(metadata_str)
    except (json.JSONDecodeError, TypeError):
        return None


def enqueue_work(
    session,
    *,
    agent_name: str,
    operation_type: str,
    lemma_id: int,
    language_code: Optional[str] = None,
    metadata: Optional[Dict] = None,
    priority: int = 0,
    skip_duplicates: bool = True,
) -> EnqueueResult:
    """Enqueue a work item for processing.

    Args:
        session: Database session
        agent_name: Name of the agent (e.g., "lape", "papuga")
        operation_type: Type of operation (e.g., "generate_measure_words")
        lemma_id: ID of the lemma to process
        language_code: Optional language code for language-specific operations
        metadata: Optional dict with additional context (serialized to JSON)
        priority: Priority level (higher = more urgent)
        skip_duplicates: If True, skip if already exists (default True)

    Returns:
        EnqueueResult with the work item and whether it was newly created
    """
    # Check for duplicates if requested
    if skip_duplicates:
        existing = (
            session.query(AgentWorkQueue)
            .filter(
                AgentWorkQueue.agent_name == agent_name,
                AgentWorkQueue.operation_type == operation_type,
                AgentWorkQueue.lemma_id == lemma_id,
                AgentWorkQueue.language_code == language_code,
                AgentWorkQueue.status.in_(WorkStatus.ACTIVE),
            )
            .first()
        )
        if existing:
            logger.debug(
                f"Work item already exists for {agent_name}/{operation_type} "
                f"lemma_id={lemma_id} (id={existing.id})"
            )
            return EnqueueResult(work_item=existing, created=False)

    # Create new work item
    work_item = AgentWorkQueue(
        agent_name=agent_name,
        operation_type=operation_type,
        lemma_id=lemma_id,
        language_code=language_code,
        status=WorkStatus.PENDING,
        priority=priority,
        metadata=_serialize_metadata(metadata),
    )
    session.add(work_item)
    session.flush()

    logger.debug(
        f"Enqueued work item {work_item.id}: {agent_name}/{operation_type} "
        f"lemma_id={lemma_id} lang={language_code}"
    )

    return EnqueueResult(work_item=work_item, created=True)


def claim_next_work(
    session,
    agent_name: Optional[str] = None,
    operation_type: Optional[str] = None,
) -> Optional[AgentWorkQueue]:
    """Atomically claim the next pending work item.

    Args:
        session: Database session
        agent_name: Optional filter by agent name
        operation_type: Optional filter by operation type

    Returns:
        The claimed work item, or None if no work available
    """
    query = session.query(AgentWorkQueue).filter(
        AgentWorkQueue.status == WorkStatus.PENDING
    )

    if agent_name:
        query = query.filter(AgentWorkQueue.agent_name == agent_name)
    if operation_type:
        query = query.filter(AgentWorkQueue.operation_type == operation_type)

    # Order by priority (desc) then created_at (asc)
    work_item = query.order_by(
        AgentWorkQueue.priority.desc(),
        AgentWorkQueue.created_at.asc(),
    ).first()

    if not work_item:
        return None

    # Claim it
    work_item.status = WorkStatus.PROCESSING
    work_item.started_at = datetime.utcnow()
    session.flush()

    logger.debug(f"Claimed work item {work_item.id}: {work_item.agent_name}/{work_item.operation_type}")

    return work_item


def mark_work_completed(
    session,
    work_item: AgentWorkQueue,
    message: str,
) -> None:
    """Mark a work item as completed.

    Args:
        session: Database session
        work_item: The work item to mark
        message: Result message
    """
    work_item.status = WorkStatus.COMPLETED
    work_item.result_message = message
    work_item.finished_at = datetime.utcnow()
    session.flush()

    logger.debug(f"Completed work item {work_item.id}: {message}")


def mark_work_failed(
    session,
    work_item: AgentWorkQueue,
    message: str,
    error_detail: Optional[str] = None,
    allow_retry: bool = False,
    max_retries: int = 3,
) -> None:
    """Mark a work item as failed.

    Args:
        session: Database session
        work_item: The work item to mark
        message: Error message
        error_detail: Optional detailed error information
        allow_retry: If True, reset to pending for retry (default False)
        max_retries: Maximum number of retries before giving up
    """
    work_item.retry_count += 1
    work_item.result_message = message
    work_item.error_detail = error_detail

    # Retry logic
    if allow_retry and work_item.retry_count < max_retries:
        work_item.status = WorkStatus.PENDING
        work_item.started_at = None
        logger.warning(
            f"Work item {work_item.id} failed, retrying (attempt {work_item.retry_count}/{max_retries})"
        )
    else:
        work_item.status = WorkStatus.FAILED
        work_item.finished_at = datetime.utcnow()
        logger.error(f"Work item {work_item.id} failed permanently: {message}")

    session.flush()


def get_work_stats(
    session,
    agent_name: Optional[str] = None,
    operation_type: Optional[str] = None,
) -> Dict[str, int]:
    """Get work queue statistics.

    Args:
        session: Database session
        agent_name: Optional filter by agent name
        operation_type: Optional filter by operation type

    Returns:
        Dictionary with counts by status
    """
    query = session.query(AgentWorkQueue)

    if agent_name:
        query = query.filter(AgentWorkQueue.agent_name == agent_name)
    if operation_type:
        query = query.filter(AgentWorkQueue.operation_type == operation_type)

    stats = {
        "pending": query.filter(AgentWorkQueue.status == WorkStatus.PENDING).count(),
        "processing": query.filter(AgentWorkQueue.status == WorkStatus.PROCESSING).count(),
        "completed": query.filter(AgentWorkQueue.status == WorkStatus.COMPLETED).count(),
        "failed": query.filter(AgentWorkQueue.status == WorkStatus.FAILED).count(),
    }
    stats["total"] = sum(stats.values())
    stats["active"] = stats["pending"] + stats["processing"]

    return stats


def get_pending_work(
    session,
    agent_name: Optional[str] = None,
    operation_type: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[AgentWorkQueue]:
    """Get pending work items (without claiming them).

    Args:
        session: Database session
        agent_name: Optional filter by agent name
        operation_type: Optional filter by operation type
        limit: Optional limit on number of items

    Returns:
        List of pending work items
    """
    query = session.query(AgentWorkQueue).filter(
        AgentWorkQueue.status == WorkStatus.PENDING
    )

    if agent_name:
        query = query.filter(AgentWorkQueue.agent_name == agent_name)
    if operation_type:
        query = query.filter(AgentWorkQueue.operation_type == operation_type)

    query = query.order_by(
        AgentWorkQueue.priority.desc(),
        AgentWorkQueue.created_at.asc(),
    )

    if limit:
        query = query.limit(limit)

    return query.all()


def clear_completed_work(
    session,
    agent_name: Optional[str] = None,
    operation_type: Optional[str] = None,
    older_than_days: Optional[int] = None,
) -> int:
    """Clear completed work items from the queue.

    Args:
        session: Database session
        agent_name: Optional filter by agent name
        operation_type: Optional filter by operation type
        older_than_days: Only clear items older than this many days

    Returns:
        Number of items deleted
    """
    query = session.query(AgentWorkQueue).filter(
        AgentWorkQueue.status == WorkStatus.COMPLETED
    )

    if agent_name:
        query = query.filter(AgentWorkQueue.agent_name == agent_name)
    if operation_type:
        query = query.filter(AgentWorkQueue.operation_type == operation_type)
    if older_than_days:
        cutoff = datetime.utcnow() - datetime.timedelta(days=older_than_days)
        query = query.filter(AgentWorkQueue.finished_at < cutoff)

    count = query.count()
    query.delete(synchronize_session=False)
    session.flush()

    logger.info(f"Cleared {count} completed work items")
    return count
