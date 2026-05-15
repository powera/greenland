#!/usr/bin/python3

"""Routes for viewing Barsukas worker tasks (BarsukasTask rows).

These are the in-process workqueue tasks created by ``enqueue_task`` and
consumed by ``workqueue.worker``. Distinct from ``batch_operations``, which
view OpenAI Batch API jobs.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from flask import Blueprint, abort, g, render_template, request
from flask.typing import ResponseReturnValue

from storage.models.schema import BarsukasTask
from workqueue.task_queue import TaskStatus

bp = Blueprint("barsukas_tasks", __name__, url_prefix="/barsukas-tasks")


_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500
_ALL_STATUSES: List[str] = [
    TaskStatus.PENDING,
    TaskStatus.RUNNING,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
]


def _parse_payload(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


@bp.route("/")
def list_tasks() -> ResponseReturnValue:
    """List Barsukas worker tasks with simple filters."""
    status_filter = request.args.get("status", "").strip()
    task_type_filter = request.args.get("task_type", "").strip()
    target_type_filter = request.args.get("target_type", "").strip()

    try:
        limit = int(request.args.get("limit", _DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT
    limit = max(1, min(limit, _MAX_LIMIT))

    query = g.db.query(BarsukasTask)
    if status_filter:
        query = query.filter(BarsukasTask.status == status_filter)
    if task_type_filter:
        query = query.filter(BarsukasTask.task_type == task_type_filter)
    if target_type_filter:
        query = query.filter(BarsukasTask.target_type == target_type_filter)

    tasks: List[BarsukasTask] = query.order_by(BarsukasTask.created_at.desc()).limit(limit).all()

    # Distinct task types and target types for filter dropdowns.
    task_types = [
        row[0]
        for row in g.db.query(BarsukasTask.task_type)
        .distinct()
        .order_by(BarsukasTask.task_type)
        .all()
        if row[0]
    ]
    target_types = [
        row[0]
        for row in g.db.query(BarsukasTask.target_type)
        .distinct()
        .order_by(BarsukasTask.target_type)
        .all()
        if row[0]
    ]

    from sqlalchemy import func

    counts_rows = (
        g.db.query(BarsukasTask.status, func.count(BarsukasTask.id))
        .group_by(BarsukasTask.status)
        .all()
    )
    status_counts: Dict[str, int] = {s: 0 for s in _ALL_STATUSES}
    for status_value, count in counts_rows:
        status_counts[status_value] = count

    return render_template(
        "barsukas_tasks/list.html",
        tasks=tasks,
        statuses=_ALL_STATUSES,
        task_types=task_types,
        target_types=target_types,
        status_filter=status_filter,
        task_type_filter=task_type_filter,
        target_type_filter=target_type_filter,
        limit=limit,
        status_counts=status_counts,
        parse_payload=_parse_payload,
    )


@bp.route("/<int:task_id>")
def view_task(task_id: int) -> ResponseReturnValue:
    """View a single Barsukas worker task."""
    task = g.db.query(BarsukasTask).filter(BarsukasTask.id == task_id).one_or_none()
    if task is None:
        abort(404)

    payload = _parse_payload(task.payload)
    payload_pretty: Optional[str]
    if payload is None:
        payload_pretty = None
    else:
        try:
            payload_pretty = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            payload_pretty = str(payload)

    sentence_ids: List[int] = []
    if isinstance(payload, dict):
        raw_ids = payload.get("sentence_ids")
        if isinstance(raw_ids, list):
            sentence_ids = [int(x) for x in raw_ids if isinstance(x, int)]

    return render_template(
        "barsukas_tasks/detail.html",
        task=task,
        payload=payload,
        payload_pretty=payload_pretty,
        sentence_ids=sentence_ids,
    )
