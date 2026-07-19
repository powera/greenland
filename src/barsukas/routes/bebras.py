#!/usr/bin/python3

"""Routes for the Bebras multi-mode UI.

Provides a unified interface for BEBRAS functionality:
1. Sentence-Word Link Processing - Process sentences and link them to vocabulary
2. Database Integrity Checking - Check database structural integrity
3. Translation Verification - Verify existing translations (with optional batch support)
"""

import json
import logging
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List

from flask import (
    Blueprint,
    Response,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue

import constants
from barsukas.helpers.flash_helpers import flash_and_log
from barsukas.helpers.agent_args import agent_db_args
from barsukas.helpers.integrity_runner import (
    INTEGRITY_CHECKS as RUNNABLE_INTEGRITY_CHECKS,
    checker_db_path,
    run_integrity_check,
)
from storage.models.schema import Lemma, Sentence

logger = logging.getLogger(__name__)

bp = Blueprint("bebras", __name__, url_prefix="/bebras")

# Track running tasks
running_tasks: Dict[str, Dict[str, Any]] = {}


# Supported languages for verification
VERIFICATION_LANGUAGES = [
    ("lt", "Lithuanian"),
    ("zh", "Chinese (Simplified)"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("de", "German"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("pt-br", "Portuguese (Brazilian)"),
    ("ru", "Russian"),
]

# Integrity check types offered by the subprocess runner ("all" is CLI-only)
INTEGRITY_CHECKS = [
    ("all", "All Checks", "Run every check below in one pass")
] + RUNNABLE_INTEGRITY_CHECKS


@bp.route("/")
def index() -> ResponseReturnValue:
    """Display the BEBRAS multi-mode interface."""
    # Get some stats for the UI
    try:
        total_lemmas = g.db.query(Lemma).filter(Lemma.guid.isnot(None)).count()
        total_sentences = g.db.query(Sentence).filter(Sentence.rejected == False).count()
    except Exception:
        total_lemmas = 0
        total_sentences = 0

    return render_template(
        "bebras/index.html",
        verification_languages=VERIFICATION_LANGUAGES,
        integrity_checks=INTEGRITY_CHECKS,
        total_lemmas=total_lemmas,
        total_sentences=total_sentences,
    )


@bp.route("/process-sentence", methods=["POST"])
def process_sentence() -> ResponseReturnValue:
    """Process a sentence to link words."""
    sentence_text = request.form.get("sentence", "").strip()
    source_language = request.form.get("source_language", "en")
    target_languages = request.form.getlist("target_languages")
    context = request.form.get("context", "").strip()
    verified = request.form.get("verified") == "true"
    output_json = request.form.get("output_json") == "true"

    if not sentence_text:
        flash_and_log("Please enter a sentence to process", "error")
        return redirect(url_for("bebras.index"))

    if not target_languages:
        target_languages = ["lt", "zh", "fr", "es"]

    # Build command
    script_path = Path(constants.AGENTS_DIR) / "bebras.py"
    args = ["python3", str(script_path)]
    args.extend(["--sentence", sentence_text])
    args.extend(["--source", source_language])
    args.extend(["--languages"] + target_languages)

    if context:
        args.extend(["--context", context])
    if verified:
        args.append("--verified")
    if output_json:
        args.append("--json")

    # Add database configuration
    _add_db_args(args)
    args.append("--yes")

    return _execute_async(args, "Sentence Processing")


@bp.route("/process-file", methods=["POST"])
def process_file() -> ResponseReturnValue:
    """Process sentences from a file."""
    file_path = request.form.get("file_path", "").strip()
    source_language = request.form.get("source_language", "en")
    target_languages = request.form.getlist("target_languages")
    verified = request.form.get("verified") == "true"
    output_json = request.form.get("output_json") == "true"

    if not file_path:
        flash_and_log("Please enter a file path", "error")
        return redirect(url_for("bebras.index"))

    if not target_languages:
        target_languages = ["lt", "zh", "fr", "es"]

    # Build command
    script_path = Path(constants.AGENTS_DIR) / "bebras.py"
    args = ["python3", str(script_path)]
    args.extend(["--file", file_path])
    args.extend(["--source", source_language])
    args.extend(["--languages"] + target_languages)

    if verified:
        args.append("--verified")
    if output_json:
        args.append("--json")

    # Add database configuration
    _add_db_args(args)
    args.append("--yes")

    return _execute_async(args, "Batch Sentence Processing")


@bp.route("/check-integrity", methods=["POST"])
def check_integrity() -> ResponseReturnValue:
    """Run database integrity checks."""
    check_type = request.form.get("check_type", "all")
    fix_issues = request.form.get("fix_issues") == "true"
    output_file = request.form.get("output_file", "").strip()

    # Build command
    script_path = Path(constants.AGENTS_DIR) / "bebras.py"
    args = ["python3", str(script_path)]
    args.append("--check-integrity")
    args.extend(["--check", check_type])

    if fix_issues:
        args.append("--fix")
    if output_file:
        args.extend(["--output", output_file])

    # The integrity CLI only understands --db-path (no --persona/--backend),
    # so point it directly at the app's SQLite database.
    db_path = checker_db_path()
    if db_path:
        args.extend(["--db-path", db_path])

    return _execute_async(args, f"Integrity Check: {check_type}")


@bp.route("/find-duplicates", methods=["POST"])
def find_duplicates() -> ResponseReturnValue:
    """Find duplicate words in-process (no subprocess)."""
    results = run_integrity_check("duplicate-words")

    return render_template(
        "bebras/duplicates.html",
        results=results,
    )


@bp.route("/verify-words", methods=["POST"])
def verify_words() -> ResponseReturnValue:
    """Verify word translations."""
    languages = request.form.getlist("languages")
    guid = request.form.get("guid", "").strip()
    limit = request.form.get("limit", "").strip()
    unverified_only = request.form.get("unverified_only") == "true"
    report_only = request.form.get("report_only") == "true"
    use_batch = request.form.get("use_batch") == "true"
    output_json = request.form.get("output_json") == "true"

    if not languages:
        languages = ["lt", "zh", "fr", "es"]

    # Build command
    script_path = Path(constants.AGENTS_DIR) / "bebras.py"
    args = ["python3", str(script_path)]
    args.append("--verify")

    if use_batch:
        # Use batch submission command
        args.append("submit-batch-words")
        args.extend(["--languages"] + languages)
        if limit:
            args.extend(["--limit", limit])
        if unverified_only:
            args.append("--unverified-only")
        task_name = "Batch Word Verification"
    else:
        # Use regular verification command
        args.append("words")
        args.extend(["--languages"] + languages)
        if guid:
            args.extend(["--guid", guid])
        if limit:
            args.extend(["--limit", limit])
        if unverified_only:
            args.append("--unverified-only")
        if report_only:
            args.append("--report-only")
        if output_json:
            args.append("--json")
        task_name = "Word Verification"

    # Add database configuration
    _add_db_args(args)
    args.append("--yes")

    return _execute_async(args, task_name)


@bp.route("/verify-sentences", methods=["POST"])
def verify_sentences() -> ResponseReturnValue:
    """Verify sentence translations."""
    languages = request.form.getlist("languages")
    sentence_id = request.form.get("sentence_id", "").strip()
    limit = request.form.get("limit", "").strip()
    unverified_only = request.form.get("unverified_only") == "true"
    report_only = request.form.get("report_only") == "true"
    check_lemma_links = request.form.get("check_lemma_links") == "true"
    use_batch = request.form.get("use_batch") == "true"
    output_json = request.form.get("output_json") == "true"

    if not languages:
        languages = ["lt", "zh", "fr", "es"]

    # Build command
    script_path = Path(constants.AGENTS_DIR) / "bebras.py"
    args = ["python3", str(script_path)]
    args.append("--verify")

    if use_batch:
        # Use batch submission command
        args.append("submit-batch-sentences")
        args.extend(["--languages"] + languages)
        if limit:
            args.extend(["--limit", limit])
        if unverified_only:
            args.append("--unverified-only")
        if check_lemma_links:
            args.append("--check-lemma-links")
        task_name = "Batch Sentence Verification"
    else:
        # Use regular verification command
        args.append("sentences")
        args.extend(["--languages"] + languages)
        if sentence_id:
            args.extend(["--sentence-id", sentence_id])
        if limit:
            args.extend(["--limit", limit])
        if unverified_only:
            args.append("--unverified-only")
        if report_only:
            args.append("--report-only")
        if check_lemma_links:
            args.append("--check-lemma-links")
        else:
            args.append("--no-check-lemma-links")
        if output_json:
            args.append("--json")
        task_name = "Sentence Verification"

    # Add database configuration
    _add_db_args(args)
    args.append("--yes")

    return _execute_async(args, task_name)


@bp.route("/output/<task_id>")
def view_output(task_id: str) -> ResponseReturnValue:
    """Display the output page for a running/completed task."""
    if task_id not in running_tasks:
        flash_and_log("Task not found or expired", "error")
        return redirect(url_for("bebras.index"))

    task = running_tasks[task_id]
    return render_template(
        "bebras/output.html",
        task_id=task_id,
        task_name=task.get("task_name", "BEBRAS Task"),
        cmdline=task.get("cmdline", ""),
    )


@bp.route("/stream/<task_id>")
def stream_output(task_id: str) -> ResponseReturnValue:
    """Stream the output of a running task using Server-Sent Events."""
    if task_id not in running_tasks:
        return Response(
            json.dumps({"error": "Task not found"}),
            status=404,
            mimetype="application/json",
        )

    def generate() -> Iterator[str]:
        """Generator function to stream output line by line."""
        task = running_tasks[task_id]
        last_line_sent = 0

        while True:
            output_lines: List[str] = task["output"]
            current_output_length = len(output_lines)

            if current_output_length > last_line_sent:
                for i in range(last_line_sent, current_output_length):
                    line_data = json.dumps({"type": "output", "line": output_lines[i]})
                    yield f"data: {line_data}\n\n"
                last_line_sent = current_output_length

            if task["complete"]:
                complete_data = json.dumps({"type": "complete", "returncode": task["returncode"]})
                yield f"data: {complete_data}\n\n"
                break

            import time

            time.sleep(0.1)

    return Response(generate(), mimetype="text/event-stream")


@bp.route("/cli-command", methods=["POST"])
def generate_cli_command() -> ResponseReturnValue:
    """Generate CLI command for the given parameters (AJAX endpoint)."""
    json_data = request.json
    if json_data is None:
        json_data = {}
    mode = json_data.get("mode", "sentence")
    params = json_data.get("params", {})

    cmd_parts = ["PYTHONPATH=src python src/agents/bebras.py"]

    if mode == "integrity":
        cmd_parts.append("--check-integrity")
        if params.get("check_type"):
            cmd_parts.append(f"--check {params['check_type']}")
        if params.get("fix_issues"):
            cmd_parts.append("--fix")
        if params.get("output_file"):
            cmd_parts.append(f"--output {params['output_file']}")

    elif mode == "verify_words":
        cmd_parts.append("--verify words")
        if params.get("languages"):
            cmd_parts.append(f"--languages {' '.join(params['languages'])}")
        if params.get("guid"):
            cmd_parts.append(f"--guid {params['guid']}")
        if params.get("limit"):
            cmd_parts.append(f"--limit {params['limit']}")
        if params.get("unverified_only"):
            cmd_parts.append("--unverified-only")
        if params.get("report_only"):
            cmd_parts.append("--report-only")

    elif mode == "verify_sentences":
        cmd_parts.append("--verify sentences")
        if params.get("languages"):
            cmd_parts.append(f"--languages {' '.join(params['languages'])}")
        if params.get("sentence_id"):
            cmd_parts.append(f"--sentence-id {params['sentence_id']}")
        if params.get("limit"):
            cmd_parts.append(f"--limit {params['limit']}")
        if params.get("unverified_only"):
            cmd_parts.append("--unverified-only")
        if params.get("report_only"):
            cmd_parts.append("--report-only")
        if params.get("check_lemma_links"):
            cmd_parts.append("--check-lemma-links")

    else:  # sentence mode
        if params.get("sentence"):
            cmd_parts.append(f'--sentence "{params["sentence"]}"')
        elif params.get("file"):
            cmd_parts.append(f"--file {params['file']}")
        if params.get("source_language"):
            cmd_parts.append(f"--source {params['source_language']}")
        if params.get("target_languages"):
            cmd_parts.append(f"--languages {' '.join(params['target_languages'])}")
        if params.get("context"):
            cmd_parts.append(f'--context "{params["context"]}"')
        if params.get("verified"):
            cmd_parts.append("--verified")

    return Response(json.dumps({"command": " ".join(cmd_parts)}), mimetype="application/json")


def _add_db_args(args: List[str]) -> None:
    """Add database configuration arguments."""
    args.extend(agent_db_args())


def _execute_async(args: List[str], task_name: str) -> ResponseReturnValue:
    """Execute a command asynchronously and redirect to output page."""
    try:
        task_id = str(uuid.uuid4())

        logger.info("Launching BEBRAS subprocess: %s", " ".join(args))
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        running_tasks[task_id] = {
            "process": process,
            "output": [],
            "complete": False,
            "returncode": None,
            "task_name": task_name,
            "cmdline": " ".join(args),
        }

        def read_output() -> None:
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    running_tasks[task_id]["output"].append(line)
                process.wait()
                running_tasks[task_id]["complete"] = True
                running_tasks[task_id]["returncode"] = process.returncode
            except Exception as e:
                running_tasks[task_id]["output"].append(f"Error reading output: {str(e)}\n")
                running_tasks[task_id]["complete"] = True
                running_tasks[task_id]["returncode"] = -1

        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()

        return redirect(url_for("bebras.view_output", task_id=task_id))

    except Exception as e:
        flash_and_log(f"Error starting task: {str(e)}", "error")
        return redirect(url_for("bebras.index"))
