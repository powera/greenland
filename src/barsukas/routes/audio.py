#!/usr/bin/python3

"""
Audio Quality Review Routes

Provides routes for managing and reviewing audio file quality.
"""

import json
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    g,
    flash,
    redirect,
    url_for,
    send_file,
    current_app,
    Response,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
import io

from wordfreq.storage.models.schema import AudioQualityReview, Lemma, LemmaDifficultyOverride
from clients.audio import Voice

bp = Blueprint("audio", __name__, url_prefix="/audio")
logger = logging.getLogger(__name__)

# Mapping from language codes to directory names
LANGUAGE_DIR_MAP = {
    "zh": "chinese",
    "lt": "lithuanian",
    "ko": "korean",
    "fr": "french",
    "de": "german",
    "es": "spanish",
    "pt": "portuguese",
    "sw": "swahili",
    "vi": "vietnamese",
}


def apply_effective_difficulty_filter(query, language_code: str, difficulty_level: int):
    """
    Apply difficulty level filter considering language-specific overrides.

    This uses a SQL COALESCE to prefer override difficulty over base difficulty.
    The query must already have Lemma joined.

    Args:
        query: SQLAlchemy query with Lemma joined
        language_code: Language code (e.g., "lt", "zh")
        difficulty_level: Target difficulty level

    Returns:
        Modified query with difficulty filter applied
    """
    from sqlalchemy import case

    # Left join with difficulty overrides for the specific language
    query = query.outerjoin(
        LemmaDifficultyOverride,
        (LemmaDifficultyOverride.lemma_id == Lemma.id)
        & (LemmaDifficultyOverride.language_code == language_code),
    )

    # Use COALESCE to prefer override difficulty, fall back to base difficulty
    # Filter by the effective difficulty level
    effective_difficulty = case(
        (
            LemmaDifficultyOverride.difficulty_level.isnot(None),
            LemmaDifficultyOverride.difficulty_level,
        ),
        else_=Lemma.difficulty_level,
    )

    query = query.filter(effective_difficulty == difficulty_level)

    return query


def link_audio_to_lemma(
    session, guid: str, expected_text: str, language_code: str
) -> Optional[int]:
    """
    Hybrid approach to link audio file to lemma.

    1. Try to match by GUID
    2. Fallback to matching by text in appropriate language translation field

    Args:
        session: Database session
        guid: GUID like "N01_001"
        expected_text: Text that should be spoken
        language_code: Language code (zh, ko, fr, etc.)

    Returns:
        Lemma ID if found, None otherwise
    """
    # Try GUID match first
    lemma = session.query(Lemma).filter_by(guid=guid).first()
    if lemma:
        return lemma.id

    # Fallback to text matching based on language
    # Map language codes to column names
    language_column_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "lt": "lithuanian_translation",
        "vi": "vietnamese_translation",
    }

    # For table-based translations (es, de, pt), query LemmaTranslation
    if language_code in ["es", "de", "pt"]:
        from wordfreq.storage.models.schema import LemmaTranslation

        translation = (
            session.query(LemmaTranslation)
            .filter_by(language_code=language_code, translation=expected_text)
            .first()
        )
        if translation:
            return translation.lemma_id

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        lemma = session.query(Lemma).filter(getattr(Lemma, column_name) == expected_text).first()
        if lemma:
            return lemma.id

    return None


def validate_audio_translation(session, guid: str, expected_text: str, language_code: str) -> dict:
    """
    Validate that audio file's expected text matches the current translation in the database.

    Args:
        session: Database session
        guid: GUID like "N01_001"
        expected_text: Text from audio file manifest
        language_code: Language code (zh, ko, fr, etc.)

    Returns:
        Dict with validation results: {
            "valid": bool,
            "current_translation": str or None,
            "mismatch": bool,
            "lemma_found": bool
        }
    """
    # Map language codes to column names
    language_column_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "lt": "lithuanian_translation",
        "vi": "vietnamese_translation",
    }

    # Try to find lemma by GUID
    lemma = session.query(Lemma).filter_by(guid=guid).first()

    if not lemma:
        return {
            "valid": False,
            "current_translation": None,
            "mismatch": False,
            "lemma_found": False,
        }

    # Get current translation from database
    current_translation = None

    # For table-based translations (es, de, pt)
    if language_code in ["es", "de", "pt"]:
        from wordfreq.storage.models.schema import LemmaTranslation

        translation = (
            session.query(LemmaTranslation)
            .filter_by(lemma_id=lemma.id, language_code=language_code)
            .first()
        )
        if translation:
            current_translation = translation.translation

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        current_translation = getattr(lemma, column_name, None)

    # Check if they match
    if current_translation is None:
        return {"valid": False, "current_translation": None, "mismatch": False, "lemma_found": True}

    mismatch = current_translation != expected_text

    return {
        "valid": not mismatch,
        "current_translation": current_translation,
        "mismatch": mismatch,
        "lemma_found": True,
    }


@bp.route("/")
def index():
    """Audio quality review dashboard."""
    # Get summary statistics
    total_files = g.db.query(AudioQualityReview).count()
    pending_review = g.db.query(AudioQualityReview).filter_by(status="pending_review").count()
    approved = g.db.query(AudioQualityReview).filter_by(status="approved").count()
    needs_replacement = g.db.query(AudioQualityReview).filter_by(status="needs_replacement").count()

    # Get counts by language
    language_counts = (
        g.db.query(AudioQualityReview.language_code, func.count(AudioQualityReview.id))
        .group_by(AudioQualityReview.language_code)
        .all()
    )

    # Get counts by voice (grouped by language/voice combination)
    voice_counts = (
        g.db.query(AudioQualityReview.display_voice, func.count(AudioQualityReview.id))
        .group_by(AudioQualityReview.language_code, AudioQualityReview.voice_name)
        .all()
    )

    return render_template(
        "audio/index.html",
        total_files=total_files,
        pending_review=pending_review,
        approved=approved,
        needs_replacement=needs_replacement,
        language_counts=dict(language_counts),
        voice_counts=dict(voice_counts),
    )


@bp.route("/import", methods=["GET", "POST"])
def import_manifest():
    """Import audio manifest file."""
    if request.method == "GET":
        # Scan for available manifests
        available_manifests = []
        audio_base = current_app.config.get("AUDIO_BASE_DIR")

        if audio_base and os.path.exists(audio_base):
            # Walk through the directory tree looking for audio_manifest.json files
            for root, dirs, files in os.walk(audio_base):
                if "audio_manifest.json" in files:
                    manifest_path = os.path.join(root, "audio_manifest.json")
                    # Get relative path from base for display
                    rel_path = os.path.relpath(root, audio_base)
                    available_manifests.append(
                        {"path": root, "display": rel_path, "full_path": manifest_path}
                    )

        return render_template("audio/import.html", available_manifests=available_manifests)

    # Handle POST - get the audio directory path
    audio_dir = request.form.get("audio_dir", "").strip()

    if not audio_dir:
        flash("Audio directory path is required", "error")
        return redirect(url_for("audio.import_manifest"))

    audio_dir_path = Path(audio_dir)

    if not audio_dir_path.exists():
        flash(f"Audio directory not found: {audio_dir}", "error")
        return redirect(url_for("audio.import_manifest"))

    if not audio_dir_path.is_dir():
        flash(f"Path is not a directory: {audio_dir}", "error")
        return redirect(url_for("audio.import_manifest"))

    # Look for audio_manifest.json in the directory
    manifest_file_path = audio_dir_path / "audio_manifest.json"

    if not manifest_file_path.exists():
        flash(f"audio_manifest.json not found in directory: {audio_dir}", "error")
        return redirect(url_for("audio.import_manifest"))

    try:
        # Parse manifest JSON from the directory
        with open(manifest_file_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        language_code = manifest_data.get("language")
        voice_name = manifest_data.get("voice")
        files_data = manifest_data.get("files", {})

        if not language_code or not voice_name:
            flash("Invalid manifest format: missing language or voice", "error")
            return redirect(url_for("audio.import_manifest"))

        # Audio directory is the provided directory
        audio_dir = str(audio_dir_path)

        # Import files
        new_count = 0
        updated_count = 0
        unchanged_count = 0
        error_count = 0

        for filename, file_info in files_data.items():
            guid = file_info.get("guid")
            text = file_info.get("text")
            md5 = file_info.get("md5")
            grammatical_form = file_info.get("grammatical_form")  # None for base forms

            if not all([guid, text, md5]):
                error_count += 1
                continue

            # Check if already exists
            existing = (
                g.db.query(AudioQualityReview)
                .filter_by(
                    guid=guid,
                    language_code=language_code,
                    voice_name=voice_name,
                    grammatical_form=grammatical_form,
                )
                .first()
            )

            if existing:
                # Update if MD5 changed
                if existing.manifest_md5 != md5:
                    existing.manifest_md5 = md5
                    existing.expected_text = text
                    existing.filename = filename
                    # Update S3 URL if MD5 changed
                    s3_cdn_base = current_app.config.get("S3_CDN_BASE_URL")
                    existing.s3_url = (
                        f"{s3_cdn_base}/{language_code}/{voice_name}/{md5}.mp3"
                        if s3_cdn_base
                        else None
                    )
                    updated_count += 1
                else:
                    unchanged_count += 1
                continue

            # Try to link to lemma
            lemma_id = link_audio_to_lemma(g.db, guid, text, language_code)

            # Calculate S3 URL from MD5 hash
            s3_cdn_base = current_app.config.get("S3_CDN_BASE_URL")
            s3_url = (
                f"{s3_cdn_base}/{language_code}/{voice_name}/{md5}.mp3" if s3_cdn_base else None
            )

            # Create new review record
            review = AudioQualityReview(
                guid=guid,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=grammatical_form,
                filename=filename,
                expected_text=text,
                manifest_md5=md5,
                s3_url=s3_url,
                lemma_id=lemma_id,
                status="pending_review",
            )

            g.db.add(review)
            new_count += 1

        g.db.commit()

        flash(
            f"Import complete: {new_count} new, {updated_count} updated, "
            f"{unchanged_count} unchanged, {error_count} errors",
            "success",
        )

        return redirect(url_for("audio.list_files"))

    except json.JSONDecodeError as e:
        flash(f"Invalid JSON format: {str(e)}", "error")
        return redirect(url_for("audio.import_manifest"))
    except Exception as e:
        g.db.rollback()
        flash(f"Error importing manifest: {str(e)}", "error")
        return redirect(url_for("audio.import_manifest"))


@bp.route("/list")
def list_files():
    """List audio files with filters and search."""
    # Get filter parameters
    language_filter = request.args.get("language", "")
    voice_filter = request.args.get("voice", "")
    status_filter = request.args.get("status", "")
    issue_filter = request.args.get("issue", "")
    search_query = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 100

    # Build query with eager loading of lemma relationship
    from sqlalchemy.orm import joinedload

    query = g.db.query(AudioQualityReview).options(joinedload(AudioQualityReview.lemma))

    if language_filter:
        query = query.filter(AudioQualityReview.language_code == language_filter)

    if voice_filter:
        # Check if voice_filter contains '/' (language/voice format)
        if "/" in voice_filter:
            query = query.filter(AudioQualityReview.display_voice == voice_filter)
        else:
            # Legacy support: filter by voice_name only
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

    if status_filter:
        query = query.filter(AudioQualityReview.status == status_filter)

    if issue_filter:
        # Filter by quality_issues JSON array containing the specified issue
        query = query.filter(AudioQualityReview.quality_issues.like(f'%"{issue_filter}"%'))

    if search_query:
        query = query.filter(
            (AudioQualityReview.expected_text.like(f"%{search_query}%"))
            | (AudioQualityReview.guid.like(f"%{search_query}%"))
        )

    # Order by GUID
    query = query.order_by(AudioQualityReview.guid)

    # Paginate
    total_count = query.count()
    audio_files = query.offset((page - 1) * per_page).limit(per_page).all()

    # Get available filter options
    languages = g.db.query(AudioQualityReview.language_code).distinct().all()
    languages = sorted([lang[0] for lang in languages])

    voices = (
        g.db.query(AudioQualityReview.display_voice)
        .distinct()
        .order_by(AudioQualityReview.display_voice)
        .all()
    )
    voices = [voice[0] for voice in voices]

    statuses = ["pending_review", "approved", "approved_with_issues", "needs_replacement"]

    # Define available issue types
    issue_types = [
        "audible_breath",
        "missing_syllable",
        "extra_syllable",
        "audible_echo",
        "volume_inconsistency",
        "background_noise",
        "pronunciation_error",
        "phoneme_confusion",
        "wrong_word",
        "unnatural_prosody",
        "clipping_distortion",
        "speed_issues",
        "translation_mismatch",
    ]

    total_pages = (total_count + per_page - 1) // per_page

    return render_template(
        "audio/list.html",
        audio_files=audio_files,
        languages=languages,
        voices=voices,
        statuses=statuses,
        issue_types=issue_types,
        language_filter=language_filter,
        voice_filter=voice_filter,
        status_filter=status_filter,
        issue_filter=issue_filter,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
    )


@bp.route("/download-filelist")
def download_filelist():
    """Download a text file containing paths to audio files matching current filters."""
    # Get filter parameters
    language_filter = request.args.get("language", "")
    voice_filter = request.args.get("voice", "")
    status_filter = request.args.get("status", "")
    issue_filter = request.args.get("issue", "")
    search_query = request.args.get("search", "").strip()

    # Build query
    query = g.db.query(AudioQualityReview)

    if language_filter:
        query = query.filter(AudioQualityReview.language_code == language_filter)

    if voice_filter:
        # Check if voice_filter contains '/' (language/voice format)
        if "/" in voice_filter:
            query = query.filter(AudioQualityReview.display_voice == voice_filter)
        else:
            # Legacy support: filter by voice_name only
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

    if status_filter:
        query = query.filter(AudioQualityReview.status == status_filter)

    if issue_filter:
        # Filter by quality_issues JSON array containing the specified issue
        query = query.filter(AudioQualityReview.quality_issues.like(f'%"{issue_filter}"%'))

    if search_query:
        query = query.filter(
            (AudioQualityReview.expected_text.like(f"%{search_query}%"))
            | (AudioQualityReview.guid.like(f"%{search_query}%"))
        )

    # Order by GUID
    query = query.order_by(AudioQualityReview.guid)

    # Get all matching files
    audio_files = query.all()

    # Get audio directory from config
    audio_base_dir = current_app.config.get("AUDIO_BASE_DIR")

    if not audio_base_dir:
        flash("Audio directory not configured", "error")
        return redirect(url_for("audio.list_files"))

    # Generate file list
    file_lines = []
    for file in audio_files:
        # Map language code to directory name (e.g., 'zh' -> 'chinese')
        language_dir = LANGUAGE_DIR_MAP.get(file.language_code, file.language_code)

        # Build file path
        file_path = Path(audio_base_dir) / language_dir / file.voice_name / file.filename

        # Add to list
        file_lines.append(str(file_path))

    # Create in-memory text file
    output = io.StringIO()
    output.write("\n".join(file_lines))
    output.seek(0)

    # Generate filename based on filters
    filename_parts = ["audio_files"]
    if language_filter:
        filename_parts.append(f"lang_{language_filter}")
    if voice_filter:
        filename_parts.append(f"voice_{voice_filter}")
    if status_filter:
        filename_parts.append(f"status_{status_filter}")
    if issue_filter:
        filename_parts.append(f"issue_{issue_filter}")

    filename = "_".join(filename_parts) + ".txt"

    # Return as downloadable file
    return Response(
        output.getvalue(),
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.route("/files/<language>/<voice>/<filename>")
def serve_audio_file(language, voice, filename):
    """
    Serve audio file - redirects to S3 CDN if available, otherwise serves from local directory.

    This route is called from the UI. It looks up the audio record by filename and redirects
    to the S3 URL if available. This allows for a seamless transition from local to S3 storage.
    """
    # Try to find the audio record by filename to get S3 URL
    from sqlalchemy.orm import joinedload

    review = (
        g.db.query(AudioQualityReview)
        .filter_by(language_code=language, voice_name=voice, filename=filename)
        .first()
    )

    # If we have an S3 URL, redirect to CDN
    if review and review.s3_url:
        return redirect(review.s3_url)

    # Fallback to local file serving
    audio_base_dir = current_app.config.get("AUDIO_BASE_DIR")

    if not audio_base_dir:
        return jsonify({"error": "Audio directory not configured and no S3 URL available"}), 500

    # Try direct language code path first (new format)
    file_path = Path(audio_base_dir) / language / voice / filename

    # If not found, try mapped language directory name (legacy format)
    if not file_path.exists():
        language_dir = LANGUAGE_DIR_MAP.get(language, language)
        file_path = Path(audio_base_dir) / language_dir / voice / filename

    logger.info(f"Serving audio file: {file_path} (exists: {file_path.exists()})")

    if not file_path.exists():
        return jsonify({"error": f"Audio file not found locally: {file_path}"}), 404

    return send_file(str(file_path), mimetype="audio/mpeg")


@bp.route("/review/<int:review_id>", methods=["GET", "POST"])
def review_file(review_id):
    """Review a single audio file."""
    review = g.db.query(AudioQualityReview).filter_by(id=review_id).first()

    if not review:
        flash("Audio review not found", "error")
        return redirect(url_for("audio.list_files"))

    if request.method == "GET":
        # Get linked lemma info if available
        lemma = None
        if review.lemma_id:
            lemma = g.db.query(Lemma).filter_by(id=review.lemma_id).first()

        return render_template("audio/review.html", review=review, lemma=lemma)

    # Handle POST - update review
    status = request.form.get("status")
    issues_json = request.form.get("quality_issues", "[]")
    notes = request.form.get("notes", "").strip()

    if status not in ["pending_review", "approved", "approved_with_issues", "needs_replacement"]:
        return jsonify({"error": "Invalid status"}), 400

    try:
        # Validate JSON
        issues = json.loads(issues_json)
        if not isinstance(issues, list):
            return jsonify({"error": "quality_issues must be an array"}), 400

        # Update review
        review.status = status
        review.quality_issues = issues_json if issues else None
        review.notes = notes if notes else None
        review.reviewed_at = datetime.utcnow()
        # TODO: Add reviewed_by when auth is implemented

        g.db.commit()

        flash("Review updated successfully", "success")

        # Redirect to next pending file or back to list
        if request.form.get("save_and_next"):
            next_review = (
                g.db.query(AudioQualityReview)
                .filter(
                    AudioQualityReview.id > review_id,
                    AudioQualityReview.language_code == review.language_code,
                    AudioQualityReview.voice_name == review.voice_name,
                    AudioQualityReview.status == "pending_review",
                )
                .order_by(AudioQualityReview.id)
                .first()
            )

            if next_review:
                return redirect(url_for("audio.review_file", review_id=next_review.id))

        return redirect(url_for("audio.list_files"))

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON for quality_issues"}), 400
    except Exception as e:
        g.db.rollback()
        flash(f"Error updating review: {str(e)}", "error")
        return redirect(url_for("audio.review_file", review_id=review_id))


@bp.route("/update/<int:review_id>", methods=["POST"])
def quick_update(review_id):
    """Quick update for inline actions (AJAX endpoint)."""
    review = g.db.query(AudioQualityReview).filter_by(id=review_id).first()

    if not review:
        return jsonify({"error": "Review not found"}), 404

    data = request.get_json()
    status = data.get("status")

    if status not in ["pending_review", "approved", "approved_with_issues", "needs_replacement"]:
        return jsonify({"error": "Invalid status"}), 400

    try:
        review.status = status
        review.reviewed_at = datetime.utcnow()
        g.db.commit()

        return jsonify({"success": True, "status": status})
    except Exception as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/rapid-review")
def rapid_review():
    """Streamlined rapid review interface with keyboard shortcuts."""
    # Get filter parameters - default to pending_review
    # Language is REQUIRED - redirect to list if not provided
    language_filter = request.args.get("language", "")
    if not language_filter:
        flash("Please select a language to begin rapid review", "warning")
        return redirect(url_for("audio.list_files"))

    voice_filter = request.args.get("voice", "")
    status_filter = request.args.get("status", "pending_review")
    subtype_filter = request.args.get("subtype", "")
    level_filter = request.args.get("level", "")

    # Build query - join with Lemma if we need subtype or level filtering
    from sqlalchemy.orm import joinedload

    if subtype_filter or level_filter:
        query = (
            g.db.query(AudioQualityReview)
            .join(Lemma, AudioQualityReview.lemma_id == Lemma.id)
            .options(joinedload(AudioQualityReview.lemma))
        )
    else:
        query = g.db.query(AudioQualityReview)

    if language_filter:
        query = query.filter(AudioQualityReview.language_code == language_filter)

    if voice_filter:
        # Check if voice_filter contains '/' (language/voice format)
        if "/" in voice_filter:
            query = query.filter(AudioQualityReview.display_voice == voice_filter)
        else:
            # Legacy support: filter by voice_name only
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

    if status_filter:
        query = query.filter(AudioQualityReview.status == status_filter)

    if subtype_filter:
        query = query.filter(Lemma.pos_subtype == subtype_filter)

    if level_filter:
        try:
            level_int = int(level_filter)
            # Apply effective difficulty filter considering language overrides
            query = apply_effective_difficulty_filter(query, language_filter, level_int)
        except ValueError:
            pass  # Ignore invalid level values

    # Order by GUID, then voice_name to ensure we go through all voices for each word
    query = query.order_by(AudioQualityReview.guid, AudioQualityReview.voice_name)

    # Get total count
    total_count = query.count()

    # Get first file
    current_review = query.first()

    # Get available filter options
    languages = g.db.query(AudioQualityReview.language_code).distinct().all()
    languages = sorted([lang[0] for lang in languages])

    voices = (
        g.db.query(AudioQualityReview.display_voice)
        .distinct()
        .order_by(AudioQualityReview.display_voice)
        .all()
    )
    voices = [voice[0] for voice in voices]

    statuses = ["pending_review", "approved", "approved_with_issues", "needs_replacement"]

    # Get available subtypes from lemmas that have audio
    subtypes = (
        g.db.query(Lemma.pos_subtype)
        .join(AudioQualityReview, AudioQualityReview.lemma_id == Lemma.id)
        .filter(Lemma.pos_subtype.isnot(None))
        .distinct()
        .all()
    )
    subtypes = sorted([st[0] for st in subtypes if st[0]])

    # Get available levels from lemmas that have audio
    levels = (
        g.db.query(Lemma.difficulty_level)
        .join(AudioQualityReview, AudioQualityReview.lemma_id == Lemma.id)
        .filter(Lemma.difficulty_level.isnot(None))
        .distinct()
        .all()
    )
    levels = sorted([lvl[0] for lvl in levels if lvl[0] is not None])

    return render_template(
        "audio/rapid_review.html",
        review=current_review,
        total_count=total_count,
        languages=languages,
        voices=voices,
        statuses=statuses,
        subtypes=subtypes,
        levels=levels,
        language_filter=language_filter,
        voice_filter=voice_filter,
        status_filter=status_filter,
        subtype_filter=subtype_filter,
        level_filter=level_filter,
    )


@bp.route("/rapid-review/submit/<int:review_id>", methods=["POST"])
def rapid_review_submit(review_id):
    """Submit rapid review and get next file (AJAX endpoint)."""
    review = g.db.query(AudioQualityReview).filter_by(id=review_id).first()

    if not review:
        return jsonify({"error": "Review not found"}), 404

    data = request.get_json()
    status = data.get("status")
    issues = data.get("quality_issues", [])

    if status not in ["pending_review", "approved", "approved_with_issues", "needs_replacement"]:
        return jsonify({"error": "Invalid status"}), 400

    try:
        # Update review
        review.status = status
        review.quality_issues = json.dumps(issues) if issues else None
        review.reviewed_at = datetime.utcnow()
        g.db.commit()

        # Get next file based on same filters
        language_filter = data.get("language", "")
        voice_filter = data.get("voice", "")
        status_filter = data.get("status_filter", "pending_review")
        subtype_filter = data.get("subtype", "")
        level_filter = data.get("level", "")

        # Build query for next file - order by (GUID, voice_name) to cycle through all voices
        # Use compound comparison: (guid, voice_name) > (current_guid, current_voice_name)
        from sqlalchemy.orm import joinedload
        from sqlalchemy import or_, and_

        if subtype_filter or level_filter:
            query = (
                g.db.query(AudioQualityReview)
                .join(Lemma, AudioQualityReview.lemma_id == Lemma.id)
                .options(joinedload(AudioQualityReview.lemma))
            )
        else:
            query = g.db.query(AudioQualityReview)

        # Compound comparison to get next in (guid, voice_name) order
        query = query.filter(
            or_(
                AudioQualityReview.guid > review.guid,
                and_(
                    AudioQualityReview.guid == review.guid,
                    AudioQualityReview.voice_name > review.voice_name,
                ),
            )
        )

        if language_filter:
            query = query.filter(AudioQualityReview.language_code == language_filter)

        if voice_filter:
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

        if status_filter:
            query = query.filter(AudioQualityReview.status == status_filter)

        if subtype_filter:
            query = query.filter(Lemma.pos_subtype == subtype_filter)

        if level_filter:
            try:
                level_int = int(level_filter)
                # Apply effective difficulty filter considering language overrides
                query = apply_effective_difficulty_filter(query, language_filter, level_int)
            except ValueError:
                pass  # Ignore invalid level values

        query = query.order_by(AudioQualityReview.guid, AudioQualityReview.voice_name)
        next_review = query.first()

        if next_review:
            # Generate pinyin for Chinese text
            pinyin_text = None
            if next_review.language_code == "zh":
                from barsukas.pinyin_helper import generate_pinyin

                pinyin_text = generate_pinyin(next_review.expected_text)

            # Validate audio file against current translation
            validation = validate_audio_translation(
                g.db, next_review.guid, next_review.expected_text, next_review.language_code
            )

            return jsonify(
                {
                    "success": True,
                    "has_next": True,
                    "next_review": {
                        "id": next_review.id,
                        "guid": next_review.guid,
                        "expected_text": next_review.expected_text,
                        "language_code": next_review.language_code,
                        "voice_name": next_review.voice_name,
                        "display_voice": next_review.display_voice,
                        "filename": next_review.filename,
                        "pinyin": pinyin_text,
                        "audio_url": url_for(
                            "audio.serve_audio_file",
                            language=next_review.language_code,
                            voice=next_review.voice_name,
                            filename=next_review.filename,
                        ),
                        "validation": validation,
                    },
                }
            )
        else:
            return jsonify(
                {"success": True, "has_next": False, "message": "No more files to review"}
            )

    except Exception as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route("/rapid-review/skip/<int:review_id>", methods=["POST"])
def rapid_review_skip(review_id):
    """Skip current review and get next file without changing status (AJAX endpoint)."""
    review = g.db.query(AudioQualityReview).filter_by(id=review_id).first()

    if not review:
        return jsonify({"error": "Review not found"}), 404

    try:
        # Don't change the review status, just get the next file
        data = request.get_json()
        language_filter = data.get("language", "")
        voice_filter = data.get("voice", "")
        status_filter = data.get("status_filter", "pending_review")
        subtype_filter = data.get("subtype", "")
        level_filter = data.get("level", "")

        # Build query for next file - order by (GUID, voice_name) to cycle through all voices
        # Use compound comparison: (guid, voice_name) > (current_guid, current_voice_name)
        from sqlalchemy.orm import joinedload
        from sqlalchemy import or_, and_

        if subtype_filter or level_filter:
            query = (
                g.db.query(AudioQualityReview)
                .join(Lemma, AudioQualityReview.lemma_id == Lemma.id)
                .options(joinedload(AudioQualityReview.lemma))
            )
        else:
            query = g.db.query(AudioQualityReview)

        # Compound comparison to get next in (guid, voice_name) order
        query = query.filter(
            or_(
                AudioQualityReview.guid > review.guid,
                and_(
                    AudioQualityReview.guid == review.guid,
                    AudioQualityReview.voice_name > review.voice_name,
                ),
            )
        )

        if language_filter:
            query = query.filter(AudioQualityReview.language_code == language_filter)

        if voice_filter:
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

        if status_filter:
            query = query.filter(AudioQualityReview.status == status_filter)

        if subtype_filter:
            query = query.filter(Lemma.pos_subtype == subtype_filter)

        if level_filter:
            try:
                level_int = int(level_filter)
                # Apply effective difficulty filter considering language overrides
                query = apply_effective_difficulty_filter(query, language_filter, level_int)
            except ValueError:
                pass  # Ignore invalid level values

        query = query.order_by(AudioQualityReview.guid, AudioQualityReview.voice_name)
        next_review = query.first()

        if next_review:
            # Generate pinyin for Chinese text
            pinyin_text = None
            if next_review.language_code == "zh":
                from barsukas.pinyin_helper import generate_pinyin

                pinyin_text = generate_pinyin(next_review.expected_text)

            # Validate audio file against current translation
            validation = validate_audio_translation(
                g.db, next_review.guid, next_review.expected_text, next_review.language_code
            )

            return jsonify(
                {
                    "success": True,
                    "has_next": True,
                    "next_review": {
                        "id": next_review.id,
                        "guid": next_review.guid,
                        "expected_text": next_review.expected_text,
                        "language_code": next_review.language_code,
                        "voice_name": next_review.voice_name,
                        "display_voice": next_review.display_voice,
                        "filename": next_review.filename,
                        "pinyin": pinyin_text,
                        "audio_url": url_for(
                            "audio.serve_audio_file",
                            language=next_review.language_code,
                            voice=next_review.voice_name,
                            filename=next_review.filename,
                        ),
                        "validation": validation,
                    },
                }
            )
        else:
            return jsonify(
                {"success": True, "has_next": False, "message": "No more files to review"}
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/rapid-review/bad-translation/<int:review_id>", methods=["POST"])
def rapid_review_bad_translation(review_id):
    """Mark translation as bad and get next file (AJAX endpoint)."""
    review = g.db.query(AudioQualityReview).filter_by(id=review_id).first()

    if not review:
        return jsonify({"error": "Review not found"}), 404

    try:
        # Mark as needs_replacement with translation_mismatch issue
        review.status = "needs_replacement"
        review.quality_issues = json.dumps(["translation_mismatch"])
        review.notes = "Translation marked as incorrect during rapid review"
        review.reviewed_at = datetime.utcnow()
        g.db.commit()

        # Get next file based on same filters
        data = request.get_json()
        language_filter = data.get("language", "")
        voice_filter = data.get("voice", "")
        status_filter = data.get("status_filter", "pending_review")
        subtype_filter = data.get("subtype", "")
        level_filter = data.get("level", "")

        # Build query for next file - order by (GUID, voice_name) to cycle through all voices
        # Use compound comparison: (guid, voice_name) > (current_guid, current_voice_name)
        from sqlalchemy.orm import joinedload
        from sqlalchemy import or_, and_

        if subtype_filter or level_filter:
            query = (
                g.db.query(AudioQualityReview)
                .join(Lemma, AudioQualityReview.lemma_id == Lemma.id)
                .options(joinedload(AudioQualityReview.lemma))
            )
        else:
            query = g.db.query(AudioQualityReview)

        # Compound comparison to get next in (guid, voice_name) order
        query = query.filter(
            or_(
                AudioQualityReview.guid > review.guid,
                and_(
                    AudioQualityReview.guid == review.guid,
                    AudioQualityReview.voice_name > review.voice_name,
                ),
            )
        )

        if language_filter:
            query = query.filter(AudioQualityReview.language_code == language_filter)

        if voice_filter:
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

        if status_filter:
            query = query.filter(AudioQualityReview.status == status_filter)

        if subtype_filter:
            query = query.filter(Lemma.pos_subtype == subtype_filter)

        if level_filter:
            try:
                level_int = int(level_filter)
                # Apply effective difficulty filter considering language overrides
                query = apply_effective_difficulty_filter(query, language_filter, level_int)
            except ValueError:
                pass  # Ignore invalid level values

        query = query.order_by(AudioQualityReview.guid, AudioQualityReview.voice_name)
        next_review = query.first()

        if next_review:
            # Generate pinyin for Chinese text
            pinyin_text = None
            if next_review.language_code == "zh":
                from barsukas.pinyin_helper import generate_pinyin

                pinyin_text = generate_pinyin(next_review.expected_text)

            # Validate audio file against current translation
            validation = validate_audio_translation(
                g.db, next_review.guid, next_review.expected_text, next_review.language_code
            )

            return jsonify(
                {
                    "success": True,
                    "has_next": True,
                    "next_review": {
                        "id": next_review.id,
                        "guid": next_review.guid,
                        "expected_text": next_review.expected_text,
                        "language_code": next_review.language_code,
                        "voice_name": next_review.voice_name,
                        "display_voice": next_review.display_voice,
                        "filename": next_review.filename,
                        "pinyin": pinyin_text,
                        "audio_url": url_for(
                            "audio.serve_audio_file",
                            language=next_review.language_code,
                            voice=next_review.voice_name,
                            filename=next_review.filename,
                        ),
                        "validation": validation,
                    },
                }
            )
        else:
            return jsonify(
                {"success": True, "has_next": False, "message": "No more files to review"}
            )

    except Exception as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Audio Generation Routes
# ============================================================================

@bp.route("/generate", methods=["GET", "POST"])
def generate():
    """Audio generation interface."""
    if request.method == "GET":
        # Show generation form
        supported_languages = ["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi"]
        available_voices = ["ash", "alloy", "nova", "ballad", "coral", "echo", "fable", "onyx", "sage", "shimmer"]

        return render_template(
            "audio/generate.html",
            supported_languages=supported_languages,
            available_voices=available_voices,
        )

    # Handle POST - trigger generation
    language_code = request.form.get("language")
    limit = request.form.get("limit", type=int)
    difficulty_level = request.form.get("difficulty_level", type=int)
    voices = request.form.getlist("voices")

    if not language_code:
        flash("Language is required", "error")
        return redirect(url_for("audio.generate"))

    if not voices:
        flash("At least one voice must be selected", "error")
        return redirect(url_for("audio.generate"))

    # Convert voice names to Voice enums
    try:
        voice_enums = [Voice(v) for v in voices]
    except ValueError as e:
        flash(f"Invalid voice: {e}", "error")
        return redirect(url_for("audio.generate"))

    # Import and run the agent
    try:
        from agents.vieversys import VieversysAgent
        import tempfile

        # Create temporary output directory
        output_dir = Path(tempfile.mkdtemp(prefix="audio_gen_"))

        agent = VieversysAgent(output_dir=str(output_dir))
        results = agent.generate_batch(
            language_code=language_code,
            limit=limit,
            difficulty_level=difficulty_level,
            voices=voice_enums,
        )

        flash(
            f"Generated audio for {results['success_count']} lemmas "
            f"({results['error_count']} errors). "
            f"Files saved to {output_dir}",
            "success" if results['error_count'] == 0 else "warning"
        )

        return redirect(url_for("audio.list_files", language=language_code, status="pending_review"))

    except Exception as e:
        flash(f"Error generating audio: {str(e)}", "error")
        return redirect(url_for("audio.generate"))


@bp.route("/generate-single/<guid>", methods=["POST"])
def generate_single(guid):
    """Generate audio for a single lemma."""
    # Support both JSON and form data
    if request.is_json:
        data = request.get_json()
        language_code = data.get("language")
        voices = data.get("voices", ["ash", "alloy", "nova"])
    else:
        language_code = request.form.get("language")
        voices = request.form.getlist("voices")
        if not voices:
            voices = ["ash", "alloy", "nova"]

    # Find lemma first so we have the lemma_id for redirects
    lemma = g.db.query(Lemma).filter_by(guid=guid).first()
    if not lemma:
        if request.is_json:
            return jsonify({"error": f"Lemma not found: {guid}"}), 404
        else:
            flash(f"Lemma not found: {guid}", "error")
            return redirect(url_for("lemmas.index"))

    if not language_code:
        if request.is_json:
            return jsonify({"error": "Language code required"}), 400
        else:
            flash("Language code required", "error")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma.id))

    try:
        # Convert voice names to Voice enums
        voice_enums = [Voice(v) for v in voices]

        # Import and run the agent
        from agents.vieversys import VieversysAgent

        # Use AUDIO_BASE_DIR for persistent storage
        audio_base_dir = current_app.config.get("AUDIO_BASE_DIR")
        if not audio_base_dir:
            raise ValueError("AUDIO_BASE_DIR not configured")

        agent = VieversysAgent(output_dir=audio_base_dir)

        result = agent.generate_audio_for_lemma(
            g.db, lemma, language_code, voice_enums, create_review_record=True
        )

        if request.is_json:
            if result["success"]:
                return jsonify({
                    "success": True,
                    "guid": guid,
                    "language": language_code,
                    "voices": result["voices"],
                    "output_dir": audio_base_dir,
                })
            else:
                return jsonify({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                }), 500
        else:
            if result["success"]:
                voice_count = len(result['voices'])
                flash(f"Successfully generated audio for {voice_count} voice(s).", "success")

                # Find the first review record we just created to redirect to it
                first_review = (
                    g.db.query(AudioQualityReview)
                    .filter_by(guid=guid, language_code=language_code, status="pending_review")
                    .order_by(AudioQualityReview.id.desc())
                    .first()
                )

                if first_review:
                    return redirect(url_for("audio.review_file", review_id=first_review.id))
                else:
                    return redirect(url_for("lemmas.view_lemma", lemma_id=lemma.id))
            else:
                flash(f"Error generating audio: {result.get('error', 'Unknown error')}", "error")
                return redirect(url_for("lemmas.view_lemma", lemma_id=lemma.id))

    except Exception as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 500
        else:
            flash(f"Error generating audio: {str(e)}", "error")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma.id))
