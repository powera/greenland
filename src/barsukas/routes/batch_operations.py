#!/usr/bin/python3

"""Routes for viewing batch operations."""

import json
from typing import Any

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    BatchRequestStatus,
    create_batch_database_session,
)
from clients.openai.batch_client import BatchStatus, OpenAIBatchClient
from barsukas.batch_poller import apply_completed_requests
from storage.models.schema import Lemma

bp = Blueprint("batch_operations", __name__, url_prefix="/batch-operations")


def batch_status(counts: dict[str, int]) -> str:
    """Keep active batches active and distinguish mixed terminal outcomes."""
    for active in ("processing", "submitted", "queued", "pending"):
        if counts.get(active, 0):
            return active
    if counts.get("failed", 0):
        return "completed with errors" if counts.get("completed", 0) else "failed"
    if counts.get("cancelled", 0):
        return "cancelled"
    return "completed" if counts.get("completed", 0) else "pending"


def failure_details(row: BatchQueue) -> dict[str, Any]:
    """Expose stored provider or application errors without another remote call."""
    raw = row.error_message or "No error details were recorded."
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        parsed = {}
    details = parsed if isinstance(parsed, dict) else {}
    return {
        "request": row,
        "code": details.get("code") or details.get("type") or "Request or processing error",
        "message": details.get("message") or raw,
        "raw": raw,
    }


@bp.route("/")
def list_batches() -> ResponseReturnValue:
    """List batch operations with filtering."""
    status_filter = request.args.get("status", "").strip()
    agent_filter = request.args.get("agent", "").strip()

    batch_session = create_batch_database_session()
    try:
        # Get unique agent names for filter dropdown
        agents = (
            batch_session.query(BatchQueue.agent_name)
            .distinct()
            .filter(BatchQueue.agent_name.isnot(None))
            .order_by(BatchQueue.agent_name)
            .all()
        )
        agents = [a[0] for a in agents if a[0]]

        # Get unique batch IDs with their info
        batch_query = (
            batch_session.query(
                BatchQueue.batch_id,
                BatchQueue.agent_name,
                BatchQueue.operation_type,
                BatchQueue.status,
                BatchQueue.submitted_at,
            )
            .filter(BatchQueue.batch_id.isnot(None))
            .order_by(BatchQueue.submitted_at.desc())
        )

        if agent_filter:
            batch_query = batch_query.filter(BatchQueue.agent_name == agent_filter)

        # Get all batch records
        all_records = batch_query.all()

        # Group by batch_id
        batches_dict: dict = {}
        for record in all_records:
            batch_id = record.batch_id
            if batch_id not in batches_dict:
                batches_dict[batch_id] = {
                    "batch_id": batch_id,
                    "agent_name": record.agent_name,
                    "operation_type": record.operation_type,
                    "submitted_at": record.submitted_at,
                    "status_counts": {},
                    "total": 0,
                }
            batches_dict[batch_id]["status_counts"][record.status] = (
                batches_dict[batch_id]["status_counts"].get(record.status, 0) + 1
            )
            batches_dict[batch_id]["total"] += 1

        # Determine overall status for each batch
        for batch_info in batches_dict.values():
            batch_info["overall_status"] = batch_status(batch_info["status_counts"])

        # Filter by status if requested
        batches = list(batches_dict.values())
        if status_filter:
            batches = [b for b in batches if b["overall_status"] == status_filter]

        # Sort by submitted_at descending
        batches.sort(key=lambda x: x["submitted_at"] or "", reverse=True)

        return render_template(
            "batch_operations/list.html",
            batches=batches,
            agents=agents,
            status_filter=status_filter,
            agent_filter=agent_filter,
            statuses=[
                "pending",
                "queued",
                "submitted",
                "processing",
                "completed",
                "completed with errors",
                "failed",
                "cancelled",
            ],
        )
    finally:
        batch_session.close()


@bp.route("/<batch_id>")
def view_batch(batch_id: str) -> ResponseReturnValue:
    """View details of a specific batch."""
    batch_session = create_batch_database_session()
    try:
        manager = BatchQueueManager(batch_session)
        summary = manager.get_batch_summary(batch_id)

        # Get individual requests for this batch
        requests = (
            batch_session.query(BatchQueue)
            .filter(BatchQueue.batch_id == batch_id)
            .order_by(BatchQueue.id)
            .all()
        )

        failures = [failure_details(row) for row in requests if row.status == "failed"]
        lemma_ids = {
            row.entity_id for row in requests if row.entity_type == "lemma" and row.entity_id
        }
        lemmas = (
            {lemma.id: lemma for lemma in g.db.query(Lemma).filter(Lemma.id.in_(lemma_ids)).all()}
            if lemma_ids
            else {}
        )
        return render_template(
            "batch_operations/detail.html",
            batch_id=batch_id,
            summary=summary,
            overall_status=batch_status(summary["status_counts"]),
            failures=failures,
            lemmas=lemmas,
            requests=requests,
        )
    finally:
        batch_session.close()


@bp.route("/<batch_id>/check-status", methods=["POST"])
def check_batch_status(batch_id: str) -> ResponseReturnValue:
    """Refresh status and retrieve available results from any terminal batch.

    Always redirects back to the detail page. Status and any retrieval outcome
    are surfaced via flashed messages.
    """
    batch_session = create_batch_database_session()
    try:
        manager = BatchQueueManager(batch_session, OpenAIBatchClient())
        try:
            info = manager.check_batch_status(batch_id)
        except Exception as exc:
            flash(f"Failed to check batch status: {exc}", "danger")
            return redirect(url_for("batch_operations.view_batch", batch_id=batch_id))

        status = info.get("status")
        flash(f"OpenAI status: {status}", "info")

        if status in (
            BatchStatus.COMPLETED.value,
            BatchStatus.EXPIRED.value,
            BatchStatus.CANCELLED.value,
            BatchStatus.FAILED.value,
        ):
            try:
                manager.retrieve_batch_results(batch_id)
                flash("Results retrieved from OpenAI.", "success")
            except Exception as exc:
                flash(f"Failed to retrieve results: {exc}", "warning")
                return redirect(url_for("batch_operations.view_batch", batch_id=batch_id))

            # Apply results per-agent to the main DB. Without this step rows are
            # marked COMPLETED in the batch DB but their translations never land
            # in the linguistic DB, and the background poller skips them since
            # it only picks up SUBMITTED/PROCESSING rows.
            completed_rows = (
                batch_session.query(BatchQueue)
                .filter(BatchQueue.batch_id == batch_id)
                .filter(BatchQueue.status == BatchRequestStatus.COMPLETED.value)
                .all()
            )
            by_agent: dict[str, list[BatchQueue]] = {}
            for row in completed_rows:
                by_agent.setdefault(row.agent_name, []).append(row)
            for agent_name, rows in by_agent.items():
                try:
                    result = apply_completed_requests(agent_name, rows, g.db, batch_id)
                    g.db.commit()
                    flash(
                        f"Applied {agent_name}: {result['updated']} updated, {result['failed']} failed.",
                        "success",
                    )
                except Exception as exc:
                    g.db.rollback()
                    flash(f"Failed to apply {agent_name} results: {exc}", "warning")

        return redirect(url_for("batch_operations.view_batch", batch_id=batch_id))
    finally:
        batch_session.close()
