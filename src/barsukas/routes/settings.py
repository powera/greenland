"""Settings and backend management routes."""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

logger = logging.getLogger(__name__)

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from werkzeug.wrappers import Response

from storage.backend import get_backend_type
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Lemma

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
    """Trigger migration from database to JSONL (form submission).

    Supports both SQLite and PostgreSQL backends.
    """
    backend_config = _get_backend_config()
    backend_type = backend_config.backend_type
    jsonl_dir: str = request.form.get("jsonl_dir", "data/working")

    # Determine direction and validate based on backend type
    if backend_type == BackendType.POSTGRES:
        direction = "postgres-to-jsonl"
        # PostgreSQL uses connection URL from config, no file path validation needed
    elif backend_type == BackendType.SQLITE:
        direction = "sqlite-to-jsonl"
        sqlite_path: str = request.form.get("sqlite_path", current_app.config.get("DB_PATH", ""))
        # Validate SQLite path exists
        if not Path(sqlite_path).exists():
            flash(f"Error: SQLite database not found: {sqlite_path}", "danger")
            return redirect(url_for("settings.index"))
    else:
        flash(f"Error: Export from {backend_type.value} backend not supported", "danger")
        return redirect(url_for("settings.index"))

    try:
        # Build command using the migrate module directly
        cmd: list[str] = [
            sys.executable,
            "-m",
            "storage.migrate",
            direction,
            "--jsonl-dir",
            jsonl_dir,
        ]

        # Add backend-specific arguments
        if backend_type == BackendType.SQLITE:
            cmd.extend(["--sqlite-path", sqlite_path])
        # PostgreSQL URL is read from env/key file automatically

        # Run migration with PYTHONPATH set to src/
        src_dir = str(Path(__file__).parent.parent.parent)
        migrate_env = {**os.environ, "PYTHONPATH": src_dir}
        logger.info("Launching agent subprocess: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=migrate_env)

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
    """Trigger migration from database to JSONL (JSON API).

    Supports both SQLite and PostgreSQL backends.
    """
    data = request.get_json()
    backend_config = _get_backend_config()
    backend_type = backend_config.backend_type

    # Get JSONL directory from request or default
    jsonl_dir: str = data.get("jsonl_dir", "data/working") if data else "data/working"

    # Determine direction based on backend type or explicit request
    requested_direction: Optional[str] = data.get("direction") if data else None

    if backend_type == BackendType.POSTGRES:
        direction = "postgres-to-jsonl"
        if requested_direction and requested_direction not in ("postgres-to-jsonl", "auto"):
            return (
                jsonify({"error": f"Cannot use {requested_direction} with PostgreSQL backend"}),
                400,
            )
    elif backend_type == BackendType.SQLITE:
        direction = "sqlite-to-jsonl"
        if requested_direction and requested_direction not in ("sqlite-to-jsonl", "auto"):
            return jsonify({"error": f"Cannot use {requested_direction} with SQLite backend"}), 400
        # Validate SQLite path
        sqlite_path: str = (
            data.get("sqlite_path", current_app.config.get("DB_PATH", "")) if data else ""
        )
        if not Path(sqlite_path).exists():
            return jsonify({"error": f"SQLite database not found: {sqlite_path}"}), 400
    else:
        return jsonify({"error": f"Export from {backend_type.value} backend not supported"}), 400

    try:
        # Build command using the migrate module directly
        cmd: list[str] = [
            sys.executable,
            "-m",
            "storage.migrate",
            direction,
            "--jsonl-dir",
            jsonl_dir,
        ]

        # Add backend-specific arguments
        if backend_type == BackendType.SQLITE:
            cmd.extend(["--sqlite-path", sqlite_path])
        # PostgreSQL URL is read from env/key file automatically

        # Run migration with PYTHONPATH set to src/
        src_dir = str(Path(__file__).parent.parent.parent)
        migrate_env = {**os.environ, "PYTHONPATH": src_dir}
        logger.info("Launching agent subprocess: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=migrate_env)

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
    elif backend_type == BackendType.POSTGRES:
        # Mask password in output
        postgres_url = backend_config.postgres_url or ""
        if "@" in postgres_url:
            _, rest = postgres_url.split("@", 1)
            info["postgres_url"] = f"postgresql://***@{rest}"
        else:
            info["postgres_url"] = postgres_url
        info["postgres_connected"] = True  # If we got here, we're connected
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

    if not current_app.config.get("ALLOW_RESTART", True):
        return jsonify({"error": "Restart is disabled in this deployment"}), 403

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


@bp.route("/sync-difficulty-levels", methods=["POST"])
def sync_difficulty_levels() -> ResponseReturnValue:
    """Sync difficulty levels from release data (data/release/lemmas) to the database.

    Reads all JSONL files from data/release/lemmas/**/*.jsonl, matches GUIDs
    to database records, and updates difficulty_level where they differ.
    """
    dry_run = request.form.get("dry_run") == "on"

    # Find all JSONL files in release data
    release_dir = Path(__file__).parent.parent.parent.parent / "data" / "release" / "lemmas"
    if not release_dir.exists():
        flash(f"Release data directory not found: {release_dir}", "danger")
        return redirect(url_for("settings.index"))

    jsonl_files = list(release_dir.glob("**/*.jsonl"))
    if not jsonl_files:
        flash(f"No JSONL files found in {release_dir}", "warning")
        return redirect(url_for("settings.index"))

    # Read all release data and build GUID -> difficulty_level mapping
    release_levels: dict[str, int] = {}
    files_read = 0
    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        guid = record.get("guid")
                        difficulty_level = record.get("difficulty_level")
                        if guid and difficulty_level is not None:
                            release_levels[guid] = difficulty_level
                    except json.JSONDecodeError:
                        continue
            files_read += 1
        except Exception as e:
            logger.warning(f"Error reading {jsonl_file}: {e}")
            continue

    if not release_levels:
        flash("No valid GUID/difficulty_level pairs found in release data", "warning")
        return redirect(url_for("settings.index"))

    # Query database for all lemmas with GUIDs
    db_lemmas = g.db.query(Lemma).filter(Lemma.guid.isnot(None)).all()

    # Find differences and update
    updated = 0
    skipped_not_found = 0
    skipped_same = 0
    changes: list[dict] = []

    for lemma in db_lemmas:
        if lemma.guid not in release_levels:
            skipped_not_found += 1
            continue

        release_level = release_levels[lemma.guid]
        if lemma.difficulty_level == release_level:
            skipped_same += 1
            continue

        changes.append(
            {
                "guid": lemma.guid,
                "label": lemma.lemma_text,
                "old_level": lemma.difficulty_level,
                "new_level": release_level,
            }
        )

        if not dry_run:
            lemma.difficulty_level = release_level
            updated += 1

    if not dry_run and updated > 0:
        g.db.commit()

    # Build result message
    if dry_run:
        if changes:
            changes_str = ", ".join(
                f"{c['guid']} ({c['label']}): {c['old_level']} → {c['new_level']}"
                for c in changes[:20]
            )
            if len(changes) > 20:
                changes_str += f" ... and {len(changes) - 20} more"
            flash(
                f"[DRY RUN] Would update {len(changes)} lemmas. "
                f"Files read: {files_read}. Release entries: {len(release_levels)}. "
                f"DB lemmas with GUID: {len(db_lemmas)}. "
                f"Changes: {changes_str}",
                "info",
            )
        else:
            flash(
                f"[DRY RUN] No changes needed. "
                f"Files read: {files_read}. Release entries: {len(release_levels)}. "
                f"DB lemmas: {len(db_lemmas)}. All levels match.",
                "success",
            )
    else:
        if updated > 0:
            flash(
                f"Updated {updated} lemma difficulty levels from release data. "
                f"Files read: {files_read}. Skipped (same): {skipped_same}. "
                f"Skipped (not in release): {skipped_not_found}.",
                "success",
            )
        else:
            flash(
                f"No updates needed. All {skipped_same} matching lemmas already have correct levels. "
                f"({skipped_not_found} DB lemmas not found in release data)",
                "info",
            )

    return redirect(url_for("settings.index"))


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
