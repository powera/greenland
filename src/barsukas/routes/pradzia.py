#!/usr/bin/python3

"""Routes for PRADZIA database initialization agent bespoke page."""

import subprocess
from pathlib import Path
from typing import Any, Dict

from config import Config
from flask import Blueprint, g, jsonify, render_template, request
from flask.typing import ResponseReturnValue

import constants
from wordfreq.storage.models.schema import Corpus, Lemma, WordFrequency, WordToken

bp = Blueprint("pradzia", __name__, url_prefix="/pradzia")


def get_database_stats() -> Dict[str, Any]:
    """Get current database statistics for display."""
    try:
        lemma_count = g.db.query(Lemma).count()
        token_count = g.db.query(WordToken).count()
        freq_count = g.db.query(WordFrequency).count()
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
    """Display the PRADZIA database initialization interface."""
    stats = get_database_stats()

    return render_template(
        "pradzia/index.html",
        stats=stats,
    )


def run_pradzia_command(args: list[str], timeout: int = 600) -> Dict[str, Any]:
    """Execute a PRADZIA command and return the result."""
    script_path = Path(constants.AGENTS_DIR) / "pradzia.py"

    if not script_path.exists():
        return {"success": False, "error": "PRADZIA agent script not found"}

    # Build full command
    full_args = ["python3", str(script_path), "--db-path", Config.DB_PATH] + args

    try:
        process = subprocess.Popen(
            full_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
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


@bp.route("/check", methods=["POST"])
def check_configuration() -> ResponseReturnValue:
    """Run configuration check (--check mode)."""
    result = run_pradzia_command(["--check"], timeout=60)
    return jsonify(result)


@bp.route("/sync-config", methods=["POST"])
def sync_configuration() -> ResponseReturnValue:
    """Sync corpus configurations to database (--sync-config mode)."""
    dry_run = request.form.get("dry_run") == "on"

    args = ["--sync-config"]
    if dry_run:
        args.append("--dry-run")

    result = run_pradzia_command(args, timeout=120)
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
    result = run_pradzia_command(args, timeout=1800)  # 30 minutes
    return jsonify(result)


@bp.route("/calc-ranks", methods=["POST"])
def calculate_ranks() -> ResponseReturnValue:
    """Calculate combined word ranks (--calc-ranks mode)."""
    dry_run = request.form.get("dry_run") == "on"

    args = ["--calc-ranks"]
    if dry_run:
        args.append("--dry-run")

    result = run_pradzia_command(args, timeout=600)  # 10 minutes
    return jsonify(result)


@bp.route("/init-full", methods=["POST"])
def full_initialization() -> ResponseReturnValue:
    """Run full database initialization (--init-full mode)."""
    dry_run = request.form.get("dry_run") == "on"

    args = ["--init-full"]
    if dry_run:
        args.append("--dry-run")

    # Full init can take a long time
    result = run_pradzia_command(args, timeout=3600)  # 60 minutes
    return jsonify(result)


@bp.route("/bootstrap", methods=["POST"])
def bootstrap_from_json() -> ResponseReturnValue:
    """Bootstrap database from trakaido JSON export (--bootstrap mode)."""
    json_path = request.form.get("json_path", "").strip()
    dry_run = request.form.get("dry_run") == "on"
    no_update_difficulty = request.form.get("no_update_difficulty") == "on"

    if not json_path:
        return jsonify({"success": False, "error": "JSON file path is required"}), 400

    args = ["--bootstrap", json_path]
    if dry_run:
        args.append("--dry-run")
    if no_update_difficulty:
        args.append("--no-update-difficulty")

    result = run_pradzia_command(args, timeout=1800)  # 30 minutes
    return jsonify(result)


@bp.route("/import-jsonl", methods=["POST"])
def import_from_jsonl() -> ResponseReturnValue:
    """Import lemmas from JSONL files (--import-jsonl mode)."""
    jsonl_dir = request.form.get("jsonl_dir", "").strip()
    dry_run = request.form.get("dry_run") == "on"

    if not jsonl_dir:
        return jsonify({"success": False, "error": "JSONL directory path is required"}), 400

    args = ["--import-jsonl", jsonl_dir]
    if dry_run:
        args.append("--dry-run")

    result = run_pradzia_command(args, timeout=1800)  # 30 minutes
    return jsonify(result)


@bp.route("/stats")
def get_stats() -> ResponseReturnValue:
    """Get current database statistics as JSON."""
    stats = get_database_stats()
    return jsonify(stats)
