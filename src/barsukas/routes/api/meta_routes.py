from datetime import datetime

from flask import g
from flask.typing import ResponseReturnValue

from barsukas.routes.api import bp
from barsukas.routes._mirror import mirrored_facade
from storage.models.schema import BarsukasTask


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@bp.route("/v1/tasks/<int:task_id>")
@mirrored_facade("/api/v1/tasks/<task_id>", "GET")
def get_task(task_id: int) -> ResponseReturnValue:
    task = g.db.query(BarsukasTask).filter(BarsukasTask.id == task_id).first()
    if task is None:
        return {"error": f"Task {task_id} not found"}, 404
    return {
        "data": {
            "id": task.id,
            "status": task.status,
            "task_type": task.task_type,
            "target_id": task.target_id,
            "created_at": _iso(task.created_at),
            "started_at": _iso(task.started_at),
            "finished_at": _iso(task.finished_at),
            "result_message": task.result_message,
            "error": task.error_detail,
        }
    }
