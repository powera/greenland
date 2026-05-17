#!/usr/bin/python3

"""Routes for viewing batch operations."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    BatchRequestStatus,
    create_batch_database_session,
)
from clients.openai.batch_client import BatchStatus, OpenAIBatchClient

bp = Blueprint("batch_operations", __name__, url_prefix="/batch-operations")


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
            counts = batch_info["status_counts"]
            if counts.get(BatchRequestStatus.FAILED.value, 0) > 0:
                batch_info["overall_status"] = "failed"
            elif counts.get(BatchRequestStatus.PROCESSING.value, 0) > 0:
                batch_info["overall_status"] = "processing"
            elif counts.get(BatchRequestStatus.SUBMITTED.value, 0) > 0:
                batch_info["overall_status"] = "submitted"
            elif counts.get(BatchRequestStatus.COMPLETED.value, 0) == batch_info["total"]:
                batch_info["overall_status"] = "completed"
            else:
                batch_info["overall_status"] = "pending"

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
            statuses=["pending", "submitted", "processing", "completed", "failed"],
        )
    finally:
        batch_session.close()


@bp.route("/<batch_id>")
def view_batch(batch_id: str) -> ResponseReturnValue:
    """View details of a specific batch."""
    batch_session = create_batch_database_session()
    try:
        manager = BatchQueueManager(batch_session, OpenAIBatchClient())
        summary = manager.get_batch_summary(batch_id)

        # Get individual requests for this batch
        requests = (
            batch_session.query(BatchQueue)
            .filter(BatchQueue.batch_id == batch_id)
            .order_by(BatchQueue.id)
            .all()
        )

        return render_template(
            "batch_operations/detail.html",
            batch_id=batch_id,
            summary=summary,
            requests=requests,
        )
    finally:
        batch_session.close()


@bp.route("/<batch_id>/check-status", methods=["POST"])
def check_batch_status(batch_id: str) -> ResponseReturnValue:
    """Refresh batch status from OpenAI and retrieve results if completed.

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

        if status == BatchStatus.COMPLETED.value:
            try:
                manager.retrieve_batch_results(batch_id)
                flash("Results retrieved from OpenAI.", "success")
            except Exception as exc:
                flash(f"Failed to retrieve results: {exc}", "warning")

        return redirect(url_for("batch_operations.view_batch", batch_id=batch_id))
    finally:
        batch_session.close()
