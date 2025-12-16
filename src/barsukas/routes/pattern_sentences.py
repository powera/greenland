#!/usr/bin/python3

"""Routes for pattern-based simple sentence generation."""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
import subprocess
from pathlib import Path
from config import Config
import constants
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS
from wordfreq.storage.models.schema import Sentence, SentenceTranslation

bp = Blueprint("pattern_sentences", __name__, url_prefix="/pattern-sentences")

# Supported languages
LANGUAGES = [
    {"code": "en", "name": "English"},
    {"code": "lt", "name": "Lithuanian"},
    {"code": "zh", "name": "Chinese"},
    {"code": "ko", "name": "Korean"},
    {"code": "fr", "name": "French"},
    {"code": "de", "name": "German"},
    {"code": "es", "name": "Spanish"},
    {"code": "pt", "name": "Portuguese"},
]


@bp.route("/")
def index():
    """Display the pattern sentence generation interface."""
    # Get statistics on existing pattern sentences
    stats = {}
    for pattern in SIMPLE_PATTERNS:
        pattern_id = pattern["pattern_id"]
        count = (
            g.db.query(Sentence)
            .filter(Sentence.source_filename == f"pattern:{pattern_id}")
            .count()
        )
        stats[pattern_id] = count

    total_sentences = sum(stats.values())

    return render_template(
        "pattern_sentences/index.html",
        patterns=SIMPLE_PATTERNS,
        languages=LANGUAGES,
        stats=stats,
        total_sentences=total_sentences,
    )


@bp.route("/generate", methods=["POST"])
def generate():
    """Execute the buivolas agent to generate pattern sentences."""
    # Get form parameters
    selected_patterns = request.form.getlist("patterns")
    selected_languages = request.form.getlist("languages")
    limit = request.form.get("limit", "10")
    dry_run = request.form.get("dry_run") == "on"

    # Validate inputs
    if not selected_languages:
        return jsonify({"success": False, "error": "No languages selected"}), 400

    # Ensure English is included
    if "en" not in selected_languages:
        selected_languages.insert(0, "en")

    # Build buivolas command
    script_path = Path(constants.AGENTS_DIR) / "buivolas.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Buivolas agent not found"}), 404

    args = ["python3", str(script_path)]

    # Add pattern selection
    if selected_patterns and "all" not in selected_patterns:
        args.append("--patterns")
        args.extend(selected_patterns)
    else:
        args.append("--all-patterns")

    # Add languages
    args.append("--languages")
    args.extend(selected_languages)

    # Add limit
    args.append("--limit")
    args.append(limit)

    # Add database path
    args.extend(["--db-path", Config.DB_PATH])

    # Add dry-run if requested
    if dry_run:
        args.append("--dry-run")

    try:
        # Execute the agent
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Wait for completion with timeout
        stdout, stderr = process.communicate(timeout=600)  # 10 min timeout

        success = process.returncode == 0

        return jsonify(
            {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": process.returncode,
            }
        )

    except subprocess.TimeoutExpired:
        process.kill()
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Generation timed out (10 minutes)",
                    "timeout": True,
                }
            ),
            408,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/view")
def view():
    """View generated pattern sentences with pagination."""
    page = request.args.get("page", 1, type=int)
    pattern_id = request.args.get("pattern_id", None)
    per_page = 20

    # Build query
    query = g.db.query(Sentence).filter(Sentence.source_filename.like("pattern:%"))

    # Filter by pattern if specified
    if pattern_id:
        query = query.filter(Sentence.source_filename == f"pattern:{pattern_id}")

    # Get total count
    total = query.count()

    # Paginate
    sentences = query.order_by(Sentence.id.desc()).limit(per_page).offset((page - 1) * per_page).all()

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "pattern_sentences/view.html",
        sentences=sentences,
        page=page,
        total_pages=total_pages,
        total=total,
        pattern_id=pattern_id,
        patterns=SIMPLE_PATTERNS,
    )
