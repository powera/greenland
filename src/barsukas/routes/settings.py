"""Settings and backend management routes."""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from werkzeug.wrappers import Response

from wordfreq.storage.backend import get_backend_type
from wordfreq.storage.backend.config import BackendType, DataSourceConfig

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

bp = Blueprint("settings", __name__, url_prefix="/settings")

# Track active requests for graceful shutdown
_active_requests = 0
_active_requests_lock = threading.Lock()
_shutdown_requested = False


def _get_backend_config() -> DataSourceConfig:
    """Get the backend config from the current app, with proper typing."""
    return current_app.backend_config  # type: ignore[attr-defined, no-any-return]


@bp.route("/")
def index() -> ResponseReturnValue:
    """Settings page."""
    backend_type = get_backend_type()
    backend_config = _get_backend_config()

    # Get environment variables
    env_backend = os.environ.get("STORAGE_BACKEND", "sqlite")
    env_sqlite_path = os.environ.get("SQLITE_DB_PATH", "")
    env_jsonl_dir = os.environ.get("JSONL_DATA_DIR", "")

    return render_template(
        "settings.html",
        current_backend=backend_type.value,
        backend_config=backend_config,
        env_backend=env_backend,
        env_sqlite_path=env_sqlite_path,
        env_jsonl_dir=env_jsonl_dir,
    )


@bp.route("/migrate-form", methods=["POST"])
def migrate_form() -> ResponseReturnValue:
    """Trigger migration from SQLite to JSONL (form submission)."""
    direction = "sqlite-to-jsonl"
    sqlite_path: str = request.form.get("sqlite_path", current_app.config.get("DB_PATH", ""))
    jsonl_dir: str = request.form.get("jsonl_dir", "data/working")

    # Validate paths
    if not Path(sqlite_path).exists():
        flash(f"Error: SQLite database not found: {sqlite_path}", "danger")
        return redirect(url_for("settings.index"))

    try:
        # Build command
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "migrate_backend.py"
        cmd = [
            sys.executable,
            str(script_path),
            direction,
            "--sqlite-path",
            sqlite_path,
            "--jsonl-dir",
            jsonl_dir,
        ]

        # Run migration
        logger.info("Launching agent subprocess: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        flash(f"Migration completed successfully! Output: {result.stdout}", "success")
        return redirect(url_for("settings.index"))

    except subprocess.CalledProcessError as e:
        flash(f"Migration failed: {e.stderr}", "danger")
        return redirect(url_for("settings.index"))
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("settings.index"))


@bp.route("/migrate", methods=["POST"])
def migrate() -> ResponseReturnValue:
    """Trigger migration from SQLite to JSONL (JSON API)."""
    data = request.get_json()
    direction: str = data.get("direction", "sqlite-to-jsonl") if data else "sqlite-to-jsonl"

    if direction != "sqlite-to-jsonl":
        return jsonify({"error": "Only sqlite-to-jsonl migration is supported currently"}), 400

    # Get paths
    sqlite_path: str = (
        data.get("sqlite_path", current_app.config.get("DB_PATH", "")) if data else ""
    )
    jsonl_dir: str = data.get("jsonl_dir", "data/working") if data else "data/working"

    # Validate paths
    if not Path(sqlite_path).exists():
        return jsonify({"error": f"SQLite database not found: {sqlite_path}"}), 400

    try:
        # Build command
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "migrate_backend.py"
        cmd: list = [
            sys.executable,
            str(script_path),
            direction,
            "--sqlite-path",
            sqlite_path,
            "--jsonl-dir",
            jsonl_dir,
        ]

        # Run migration
        logger.info("Launching agent subprocess: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        return jsonify(
            {
                "success": True,
                "message": "Migration completed successfully",
                "output": result.stdout,
            }
        )

    except subprocess.CalledProcessError as e:
        return (
            jsonify(
                {
                    "error": "Migration failed",
                    "stdout": e.stdout,
                    "stderr": e.stderr,
                }
            ),
            500,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/backend/switch", methods=["POST"])
def switch_backend() -> ResponseReturnValue:
    """Switch to a different backend.

    Note: This doesn't actually switch the backend in the current process.
    It just provides instructions for how to restart with a different backend.
    """
    data = request.get_json()
    target_backend = data.get("backend", "sqlite")

    if target_backend not in ["sqlite", "jsonl"]:
        return jsonify({"error": "Invalid backend type"}), 400

    current_backend = get_backend_type().value

    if target_backend == current_backend:
        return jsonify({"message": "Already using that backend"}), 200

    # Provide instructions for switching
    instructions = {
        "message": f"To switch to {target_backend} backend, restart Barsukas with:",
        "command": f"STORAGE_BACKEND={target_backend} python src/barsukas/app.py",
    }

    if target_backend == "jsonl":
        instructions["note"] = "Make sure to run the migration first if you haven't already"

    return jsonify(instructions), 200


@bp.route("/backend/info", methods=["GET"])
def backend_info() -> ResponseReturnValue:
    """Get information about the current backend."""
    backend_type = get_backend_type()
    backend_config = _get_backend_config()

    info: dict = {
        "backend_type": backend_type.value,
        "config": str(backend_config),
    }

    if backend_type == BackendType.SQLITE:
        sqlite_path = backend_config.sqlite_path
        assert sqlite_path is not None
        info["sqlite_path"] = sqlite_path
        info["sqlite_exists"] = Path(sqlite_path).exists()
        if info["sqlite_exists"]:
            info["sqlite_size"] = Path(sqlite_path).stat().st_size
    else:
        jsonl_dir = backend_config.jsonl_data_dir
        assert jsonl_dir is not None
        info["jsonl_dir"] = jsonl_dir
        info["jsonl_exists"] = Path(jsonl_dir).exists()

    return jsonify(info)


@bp.route("/restart", methods=["POST"])
def restart() -> ResponseReturnValue:
    """Initiate a graceful restart of the Barsukas process.

    This endpoint:
    1. Returns immediately to the client
    2. Waits for all in-flight requests to complete
    3. Restarts the process with the same arguments
    """
    global _shutdown_requested

    if _shutdown_requested:
        return jsonify({"error": "Restart already in progress"}), 409

    _shutdown_requested = True

    # Start restart in background thread
    def do_restart() -> None:
        # Wait a moment for this response to be sent
        time.sleep(0.5)

        # Wait for all other requests to complete
        max_wait = 300  # 5 minutes max wait
        start_time = time.time()

        while time.time() - start_time < max_wait:
            with _active_requests_lock:
                # Only this request (the restart request) should remain
                # (Status checks are not tracked, so they don't count)
                if _active_requests <= 1:
                    break
            time.sleep(0.1)

        print("\n" + "=" * 50)
        print("Graceful restart initiated")
        print("All requests completed, shutting down...")
        print("=" * 50 + "\n")

        # Flush output
        sys.stdout.flush()
        sys.stderr.flush()

        # Exit with code 42 to signal the launch script to restart
        # This is cleaner than fork/exec and lets the OS fully clean up
        os._exit(42)

    restart_thread = threading.Thread(target=do_restart, daemon=True)
    restart_thread.start()

    return jsonify(
        {
            "success": True,
            "message": "Restart initiated. Waiting for active requests to complete...",
        }
    )


@bp.route("/restart/status", methods=["GET"])
def restart_status() -> ResponseReturnValue:
    """Check the status of an ongoing restart.

    Note: This endpoint is exempt from request tracking to avoid
    interfering with the restart process.
    """
    with _active_requests_lock:
        active = _active_requests

    return jsonify(
        {
            "shutdown_requested": _shutdown_requested,
            "active_requests": active,
            "ready_to_restart": active <= 1 if _shutdown_requested else False,
        }
    )


@bp.before_request
def track_request_start() -> None:
    """Track when a request starts.

    Exempt the restart/status endpoint from tracking so polling
    doesn't prevent shutdown.
    """
    global _active_requests

    # Don't track status checks during restart
    if request.endpoint == "settings.restart_status":
        return

    with _active_requests_lock:
        _active_requests += 1


@bp.after_request
def track_request_end(response: Response) -> Response:
    """Track when a request ends."""
    global _active_requests

    # Don't track status checks during restart
    if request.endpoint == "settings.restart_status":
        return response

    with _active_requests_lock:
        _active_requests -= 1
    return response
