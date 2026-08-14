#!/usr/bin/python3

"""Routes for database maintenance and corpus administration."""

import logging
import subprocess
import threading
import uuid
from typing import Any, Dict, List, cast

logger = logging.getLogger(__name__)

from flask import Blueprint, g, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

import constants
from barsukas.routes.agents_launcher import running_tasks
from barsukas.helpers.agent_args import agent_db_args
from storage.models.schema import Corpus, ExternalLexemeAnnotation, Lemma, WordToken

bp = Blueprint("pradzia", __name__, url_prefix="/pradzia")


def get_database_stats() -> Dict[str, Any]:
    """Get current database statistics for display."""
    try:
        lemma_count = g.db.query(Lemma).count()
        token_count = g.db.query(WordToken).count()
        freq_count = g.db.query(ExternalLexemeAnnotation).count()
        corpus_count = g.db.query(Corpus).count()
        enabled_corpus_count = g.db.query(Corpus).filter(Corpus.enabled == True).count()

        # Get corpus details
        corpora = g.db.query(Corpus).all()
        corpus_details = [
            {
                "name": c.name,
                "description": c.description,
                "enabled": c.enabled,
                "corpus_weight": c.corpus_weight,
                "max_unknown_rank": c.max_unknown_rank,
            }
            for c in corpora
        ]

        # Check if database appears initialized
        is_initialized = lemma_count > 0 or token_count > 0

        return {
            "lemma_count": lemma_count,
            "token_count": token_count,
            "freq_count": freq_count,
            "corpus_count": corpus_count,
            "enabled_corpus_count": enabled_corpus_count,
            "corpus_details": corpus_details,
            "is_initialized": is_initialized,
        }
    except Exception as e:
        return {
            "error": str(e),
            "lemma_count": 0,
            "token_count": 0,
            "freq_count": 0,
            "corpus_count": 0,
            "enabled_corpus_count": 0,
            "corpus_details": [],
            "is_initialized": False,
        }


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display the database-administration interface."""
    stats = get_database_stats()

    return render_template(
        "pradzia/index.html",
        stats=stats,
    )


def run_database_admin_command(args: list[str], timeout: int = 600) -> Dict[str, Any]:
    """Execute a database-administration command and return the result."""
    # Build full command with appropriate backend configuration
    full_args = ["python3", "-m", "storage.admin"]
    full_args.extend(agent_db_args())
    full_args.extend(args)

    try:
        logger.info("Launching database-admin subprocess: %s", " ".join(full_args))
        process = subprocess.Popen(
            full_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=constants.SRC_DIR,
        )
        stdout, stderr = process.communicate(timeout=timeout)

        return {
            "success": process.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": process.returncode,
            "command": " ".join(full_args),
        }
    except subprocess.TimeoutExpired:
        process.kill()
        return {
            "success": False,
            "error": f"Command timed out ({timeout} seconds)",
            "timeout": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def start_database_admin_task(args: list[str], operation_name: str) -> str:
    """Start a database-administration command and return the task ID.

    Uses the shared running_tasks dict from agents_launcher for task tracking
    and SSE streaming.
    """
    # Build full command with appropriate backend configuration
    full_args = ["python3", "-m", "storage.admin"]
    full_args.extend(agent_db_args())
    full_args.extend(args)

    # Generate unique task ID
    task_id = str(uuid.uuid4())

    # Start the process
    logger.info("Launching database-admin subprocess: %s", " ".join(full_args))
    process = subprocess.Popen(
        full_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Combine stderr into stdout for unified streaming
        text=True,
        bufsize=1,  # Line buffered
        universal_newlines=True,
        cwd=constants.SRC_DIR,
    )

    # Store task info in shared running_tasks dict (from agents_launcher)
    running_tasks[task_id] = {
        "process": process,
        "output": [],
        "complete": False,
        "returncode": None,
        "agent_name": "DATABASE_ADMIN",
        "agent_display_name": operation_name,
        "cmdline": " ".join(full_args),
    }

    # Start background thread to read output
    def read_output() -> None:
        try:
            assert process.stdout is not None, "process.stdout should not be None"
            for line in process.stdout:
                output_list = cast(List[str], running_tasks[task_id]["output"])
                output_list.append(line)
            process.wait()
            running_tasks[task_id]["complete"] = True
            running_tasks[task_id]["returncode"] = process.returncode
        except Exception as e:
            output_list_err = cast(List[str], running_tasks[task_id]["output"])
            output_list_err.append(f"Error reading output: {str(e)}\n")
            running_tasks[task_id]["complete"] = True
            running_tasks[task_id]["returncode"] = -1

    thread = threading.Thread(target=read_output, daemon=True)
    thread.start()

    return task_id


@bp.route("/check", methods=["POST"])
def check_configuration() -> ResponseReturnValue:
    """Run configuration check (--check mode)."""
    result = run_database_admin_command(["--check"], timeout=60)
    return jsonify(result)


@bp.route("/sync-config", methods=["POST"])
def sync_configuration() -> ResponseReturnValue:
    """Sync corpus configurations to database (--sync-config mode)."""
    dry_run = request.form.get("dry_run") == "on"

    args = ["--sync-config"]
    if dry_run:
        args.append("--dry-run")

    result = run_database_admin_command(args, timeout=120)
    return jsonify(result)


@bp.route("/load-corpora", methods=["POST"])
def load_corpora() -> ResponseReturnValue:
    """Load corpus data into database (--load mode)."""
    dry_run = request.form.get("dry_run") == "on"
    corpus_names = request.form.getlist("corpora")

    args = ["--load"]
    if corpus_names:
        args.extend(corpus_names)
    if dry_run:
        args.append("--dry-run")

    # Loading corpora can take a while
    result = run_database_admin_command(args, timeout=1800)  # 30 minutes
    return jsonify(result)


@bp.route("/calc-ranks", methods=["POST"])
def calculate_ranks() -> ResponseReturnValue:
    """Calculate combined word ranks (--calc-ranks mode)."""
    dry_run = request.form.get("dry_run") == "on"

    args = ["--calc-ranks"]
    if dry_run:
        args.append("--dry-run")

    result = run_database_admin_command(args, timeout=600)  # 10 minutes
    return jsonify(result)


@bp.route("/stats")
def get_stats() -> ResponseReturnValue:
    """Get current database statistics as JSON."""
    stats = get_database_stats()
    return jsonify(stats)


# =============================================================================
# Execute routes - Start async tasks and redirect to status page
# =============================================================================


@bp.route("/execute/check", methods=["POST"])
def execute_check() -> ResponseReturnValue:
    """Execute configuration check and redirect to status page."""
    task_id = start_database_admin_task(["--check"], "Check Configuration")
    return redirect(url_for("agents_launcher.view_output", task_id=task_id))


@bp.route("/execute/sync-config", methods=["POST"])
def execute_sync_config() -> ResponseReturnValue:
    """Execute sync configuration and redirect to status page."""
    dry_run = request.form.get("dry_run") == "on"

    args = ["--sync-config"]
    if dry_run:
        args.append("--dry-run")

    operation_name = "Sync Configuration" + (" (Dry Run)" if dry_run else "")
    task_id = start_database_admin_task(args, operation_name)
    return redirect(url_for("agents_launcher.view_output", task_id=task_id))


@bp.route("/execute/load-corpora", methods=["POST"])
def execute_load_corpora() -> ResponseReturnValue:
    """Execute load corpora and redirect to status page."""
    dry_run = request.form.get("dry_run") == "on"
    corpus_names = request.form.getlist("corpora")

    args = ["--load"]
    if corpus_names:
        args.extend(corpus_names)
    if dry_run:
        args.append("--dry-run")

    operation_name = "Load Corpora" + (" (Dry Run)" if dry_run else "")
    task_id = start_database_admin_task(args, operation_name)
    return redirect(url_for("agents_launcher.view_output", task_id=task_id))


@bp.route("/execute/calc-ranks", methods=["POST"])
def execute_calc_ranks() -> ResponseReturnValue:
    """Execute calculate ranks and redirect to status page."""
    dry_run = request.form.get("dry_run") == "on"

    args = ["--calc-ranks"]
    if dry_run:
        args.append("--dry-run")

    operation_name = "Calculate Ranks" + (" (Dry Run)" if dry_run else "")
    task_id = start_database_admin_task(args, operation_name)
    return redirect(url_for("agents_launcher.view_output", task_id=task_id))
