"""Settings and backend management routes."""

import os
import subprocess
import sys
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app

from wordfreq.storage.backend import get_backend_type
from wordfreq.storage.backend.config import BackendType

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/")
def index():
    """Settings page."""
    backend_type = get_backend_type()
    backend_config = current_app.backend_config

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
def migrate_form():
    """Trigger migration from SQLite to JSONL (form submission)."""
    direction = "sqlite-to-jsonl"
    sqlite_path = request.form.get("sqlite_path", current_app.config.get("DB_PATH"))
    jsonl_dir = request.form.get("jsonl_dir", "data/working")

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
def migrate():
    """Trigger migration from SQLite to JSONL (JSON API)."""
    data = request.get_json()
    direction = data.get("direction", "sqlite-to-jsonl")

    if direction != "sqlite-to-jsonl":
        return jsonify({"error": "Only sqlite-to-jsonl migration is supported currently"}), 400

    # Get paths
    sqlite_path = data.get("sqlite_path", current_app.config.get("DB_PATH"))
    jsonl_dir = data.get("jsonl_dir", "data/working")

    # Validate paths
    if not Path(sqlite_path).exists():
        return jsonify({"error": f"SQLite database not found: {sqlite_path}"}), 400

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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        return jsonify({
            "success": True,
            "message": "Migration completed successfully",
            "output": result.stdout,
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            "error": "Migration failed",
            "stdout": e.stdout,
            "stderr": e.stderr,
        }), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/backend/switch", methods=["POST"])
def switch_backend():
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

    return jsonify(instructions)


@bp.route("/backend/info", methods=["GET"])
def backend_info():
    """Get information about the current backend."""
    backend_type = get_backend_type()
    backend_config = current_app.backend_config

    info = {
        "backend_type": backend_type.value,
        "config": str(backend_config),
    }

    if backend_type == BackendType.SQLITE:
        info["sqlite_path"] = backend_config.sqlite_path
        info["sqlite_exists"] = Path(backend_config.sqlite_path).exists()
        if info["sqlite_exists"]:
            info["sqlite_size"] = Path(backend_config.sqlite_path).stat().st_size
    else:
        info["jsonl_dir"] = backend_config.jsonl_data_dir
        info["jsonl_exists"] = Path(backend_config.jsonl_data_dir).exists()

    return jsonify(info)
