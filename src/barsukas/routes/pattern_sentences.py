#!/usr/bin/python3

"""Routes for pattern-based simple sentence generation."""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
import subprocess
from pathlib import Path
from config import Config
import constants
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS
from wordfreq.storage.models.schema import Sentence, SentenceTranslation, SentenceWord, Lemma

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


@bp.route("/generate-candidates", methods=["POST"])
def generate_candidates():
    """Execute the buivolas agent to generate candidate sentences (without translations)."""
    # Get form parameters
    selected_patterns = request.form.getlist("patterns")
    limit = request.form.get("limit", "10")
    dry_run = request.form.get("dry_run") == "on"

    # Build buivolas command
    script_path = Path(constants.AGENTS_DIR) / "buivolas.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Buivolas agent not found"}), 404

    # Global args before subcommand
    args = ["python3", str(script_path)]

    # Add database path (before subcommand)
    args.extend(["--db-path", Config.DB_PATH])

    # Add dry-run if requested (before subcommand)
    if dry_run:
        args.append("--dry-run")

    # Add subcommand
    args.append("generate-candidates")

    # Add pattern selection
    if selected_patterns and "all" not in selected_patterns:
        args.append("--patterns")
        args.extend(selected_patterns)
    else:
        args.append("--all-patterns")

    # Add limit
    if limit:
        args.append("--limit")
        args.append(limit)

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


@bp.route("/submit-batch", methods=["POST"])
def submit_batch():
    """Submit a batch translation job for untranslated sentences."""
    # Get form parameters
    selected_languages = request.form.getlist("languages")
    limit = request.form.get("limit", "")
    pattern_id = request.form.get("pattern_id", "")

    # Validate inputs
    if not selected_languages:
        return jsonify({"success": False, "error": "No languages selected"}), 400

    # Build buivolas command
    script_path = Path(constants.AGENTS_DIR) / "buivolas.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Buivolas agent not found"}), 404

    # Global args before subcommand
    args = ["python3", str(script_path)]

    # Add database path (before subcommand)
    args.extend(["--db-path", Config.DB_PATH])

    # Add subcommand
    args.extend(["submit-batch", "--languages"])
    args.extend(selected_languages)

    # Add limit if specified
    if limit:
        args.append("--limit")
        args.append(limit)

    # Add pattern filter if specified
    if pattern_id:
        args.append("--pattern-id")
        args.append(pattern_id)

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
                    "error": "Batch submission timed out (10 minutes)",
                    "timeout": True,
                }
            ),
            408,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/batch-status")
def batch_status():
    """Get status of all active batches."""
    script_path = Path(constants.AGENTS_DIR) / "buivolas.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Buivolas agent not found"}), 404

    args = ["python3", str(script_path), "--db-path", Config.DB_PATH, "list-batches"]

    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=30)

        success = process.returncode == 0

        return jsonify(
            {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/check-batch/<batch_id>")
def check_batch(batch_id):
    """Check status of a specific batch and retrieve results if completed."""
    script_path = Path(constants.AGENTS_DIR) / "buivolas.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Buivolas agent not found"}), 404

    # First check the status
    args = ["python3", str(script_path), "--db-path", Config.DB_PATH, "check-batch", "--batch-id", batch_id]

    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=30)

        success = process.returncode == 0

        # Parse output to determine if batch is completed
        # Note: logging output goes to stderr, not stdout
        is_completed = "Status: completed" in stderr

        response_data = {
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
            "is_completed": is_completed,
            "batch_id": batch_id,
        }

        # If completed, automatically retrieve results
        if is_completed:
            retrieve_args = ["python3", str(script_path), "--db-path", Config.DB_PATH, "retrieve-batch", "--batch-id", batch_id]
            retrieve_process = subprocess.Popen(retrieve_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            retrieve_stdout, retrieve_stderr = retrieve_process.communicate(timeout=300)  # 5 min timeout

            response_data["retrieve_success"] = retrieve_process.returncode == 0
            response_data["retrieve_stdout"] = retrieve_stdout
            response_data["retrieve_stderr"] = retrieve_stderr

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/retrieve-batch/<batch_id>", methods=["POST"])
def retrieve_batch(batch_id):
    """Retrieve and apply results from a completed batch."""
    script_path = Path(constants.AGENTS_DIR) / "buivolas.py"

    if not script_path.exists():
        return jsonify({"success": False, "error": f"Buivolas agent not found"}), 404

    args = ["python3", str(script_path), "--db-path", Config.DB_PATH, "retrieve-batch", "--batch-id", batch_id]

    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=300)  # 5 min timeout

        success = process.returncode == 0

        return jsonify(
            {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
            }
        )

    except subprocess.TimeoutExpired:
        process.kill()
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Batch retrieval timed out (5 minutes)",
                    "timeout": True,
                }
            ),
            408,
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/<int:sentence_id>/reject", methods=["POST"])
def reject_sentence(sentence_id):
    """Mark a sentence as rejected so it won't be regenerated."""
    sentence = g.db.query(Sentence).get(sentence_id)
    if not sentence:
        flash("Sentence not found", "error")
        return redirect(url_for("pattern_sentences.view"))

    try:
        sentence.rejected = True
        g.db.commit()
        flash(f"Sentence #{sentence_id} marked as rejected", "success")
    except Exception as e:
        flash(f"Error rejecting sentence: {e}", "error")
        g.db.rollback()

    # Redirect back to the view page with current filters
    return redirect(request.referrer or url_for("pattern_sentences.view"))


@bp.route("/view")
def view():
    """View generated pattern sentences with pagination."""
    page = request.args.get("page", 1, type=int)
    pattern_id = request.args.get("pattern_id", None)
    language_code = request.args.get("language_code", None)
    lemma_guid = request.args.get("lemma_guid", "").strip() or None
    per_page = 20

    # Build query
    query = g.db.query(Sentence).filter(Sentence.source_filename.like("pattern:%"))

    # Filter by pattern if specified
    if pattern_id:
        query = query.filter(Sentence.source_filename == f"pattern:{pattern_id}")

    # Filter by language if specified (only show sentences with translation in that language)
    if language_code:
        translation_subquery = g.db.query(SentenceTranslation.sentence_id).filter(
            SentenceTranslation.language_code == language_code
        )
        query = query.filter(Sentence.id.in_(translation_subquery))

    # Filter by lemma GUID if specified (only show sentences containing that lemma)
    if lemma_guid:
        # First find the lemma by GUID
        lemma = g.db.query(Lemma).filter(Lemma.guid == lemma_guid).first()
        if lemma:
            # Find sentences that use this lemma
            sentence_word_subquery = g.db.query(SentenceWord.sentence_id).filter(
                SentenceWord.lemma_id == lemma.id
            )
            query = query.filter(Sentence.id.in_(sentence_word_subquery))
        else:
            # If lemma GUID not found, return no results
            query = query.filter(Sentence.id == -1)

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
        language_code=language_code,
        lemma_guid=lemma_guid,
        patterns=SIMPLE_PATTERNS,
        languages=LANGUAGES,
    )
