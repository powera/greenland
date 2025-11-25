#!/usr/bin/python3

"""
Audio Quality Review Routes

Provides routes for managing and reviewing audio file quality.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from flask import Blueprint, render_template, request, jsonify, g, flash, redirect, url_for, send_file, current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from wordfreq.storage.models.schema import AudioQualityReview, Lemma

bp = Blueprint("audio", __name__, url_prefix="/audio")

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


def link_audio_to_lemma(session, guid: str, expected_text: str, language_code: str) -> Optional[int]:
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
        translation = session.query(LemmaTranslation).filter_by(
            language_code=language_code,
            translation=expected_text
        ).first()
        if translation:
            return translation.lemma_id

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        lemma = session.query(Lemma).filter(
            getattr(Lemma, column_name) == expected_text
        ).first()
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
            "lemma_found": False
        }

    # Get current translation from database
    current_translation = None

    # For table-based translations (es, de, pt)
    if language_code in ["es", "de", "pt"]:
        from wordfreq.storage.models.schema import LemmaTranslation
        translation = session.query(LemmaTranslation).filter_by(
            lemma_id=lemma.id,
            language_code=language_code
        ).first()
        if translation:
            current_translation = translation.translation

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        current_translation = getattr(lemma, column_name, None)

    # Check if they match
    if current_translation is None:
        return {
            "valid": False,
            "current_translation": None,
            "mismatch": False,
            "lemma_found": True
        }

    mismatch = current_translation != expected_text

    return {
        "valid": not mismatch,
        "current_translation": current_translation,
        "mismatch": mismatch,
        "lemma_found": True
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
    language_counts = g.db.query(
        AudioQualityReview.language_code,
        func.count(AudioQualityReview.id)
    ).group_by(AudioQualityReview.language_code).all()

    # Get counts by voice
    voice_counts = g.db.query(
        AudioQualityReview.voice_name,
        func.count(AudioQualityReview.id)
    ).group_by(AudioQualityReview.voice_name).all()

    return render_template(
        "audio/index.html",
        total_files=total_files,
        pending_review=pending_review,
        approved=approved,
        needs_replacement=needs_replacement,
        language_counts=dict(language_counts),
        voice_counts=dict(voice_counts)
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
                    available_manifests.append({
                        "path": root,
                        "display": rel_path,
                        "full_path": manifest_path
                    })

        return render_template("audio/import.html", available_manifests=available_manifests)

    # Handle POST - get the audio directory path
    audio_dir = request.form.get("audio_dir", "").strip()

    if not audio_dir:
        flash("Audio directory path is required", "error")
        return redirect(url_for("audio.import_manifest"))

    audio_dir_path = Path(audio_dir)

    if not audio_dir_path.exists():
        flash(f'Audio directory not found: {audio_dir}', "error")
        return redirect(url_for("audio.import_manifest"))

    if not audio_dir_path.is_dir():
        flash(f'Path is not a directory: {audio_dir}', "error")
        return redirect(url_for("audio.import_manifest"))

    # Look for audio_manifest.json in the directory
    manifest_file_path = audio_dir_path / "audio_manifest.json"

    if not manifest_file_path.exists():
        flash(f'audio_manifest.json not found in directory: {audio_dir}', "error")
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
        imported_count = 0
        skipped_count = 0
        error_count = 0

        for filename, file_info in files_data.items():
            guid = file_info.get("guid")
            text = file_info.get("text")
            md5 = file_info.get("md5")

            if not all([guid, text, md5]):
                error_count += 1
                continue

            # Check if already exists
            existing = g.db.query(AudioQualityReview).filter_by(
                guid=guid,
                language_code=language_code,
                voice_name=voice_name
            ).first()

            if existing:
                # Update MD5 if changed
                if existing.manifest_md5 != md5:
                    existing.manifest_md5 = md5
                    existing.expected_text = text
                    existing.filename = filename
                    imported_count += 1
                else:
                    skipped_count += 1
                continue

            # Try to link to lemma
            lemma_id = link_audio_to_lemma(g.db, guid, text, language_code)

            # Create new review record
            review = AudioQualityReview(
                guid=guid,
                language_code=language_code,
                voice_name=voice_name,
                filename=filename,
                expected_text=text,
                manifest_md5=md5,
                lemma_id=lemma_id,
                status="pending_review"
            )

            g.db.add(review)
            imported_count += 1

        g.db.commit()

        flash(
            f'Import complete: {imported_count} files imported, '
            f'{skipped_count} skipped (already exist), '
            f'{error_count} errors',
            "success"
        )

        return redirect(url_for("audio.list_files"))

    except json.JSONDecodeError as e:
        flash(f'Invalid JSON format: {str(e)}', "error")
        return redirect(url_for("audio.import_manifest"))
    except Exception as e:
        g.db.rollback()
        flash(f'Error importing manifest: {str(e)}', "error")
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
        query = query.filter(AudioQualityReview.voice_name == voice_filter)

    if status_filter:
        query = query.filter(AudioQualityReview.status == status_filter)

    if issue_filter:
        # Filter by quality_issues JSON array containing the specified issue
        query = query.filter(AudioQualityReview.quality_issues.like(f'%"{issue_filter}"%'))

    if search_query:
        query = query.filter(
            (AudioQualityReview.expected_text.like(f'%{search_query}%')) |
            (AudioQualityReview.guid.like(f'%{search_query}%'))
        )

    # Order by GUID
    query = query.order_by(AudioQualityReview.guid)

    # Paginate
    total_count = query.count()
    audio_files = query.offset((page - 1) * per_page).limit(per_page).all()

    # Get available filter options
    languages = g.db.query(AudioQualityReview.language_code).distinct().all()
    languages = sorted([lang[0] for lang in languages])

    voices = g.db.query(AudioQualityReview.voice_name).distinct().all()
    voices = sorted([voice[0] for voice in voices])

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
        "translation_mismatch"
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
        total_pages=total_pages
    )


@bp.route("/files/<language>/<voice>/<filename>")
def serve_audio_file(language, voice, filename):
    """Serve audio file from local directory."""
    # Get audio directory from config
    audio_base_dir = current_app.config.get("AUDIO_BASE_DIR")

    if not audio_base_dir:
        return jsonify({"error": "Audio directory not configured"}), 500

    # Map language code to directory name (e.g., 'zh' -> 'chinese')
    language_dir = LANGUAGE_DIR_MAP.get(language, language)

    # Build file path
    file_path = Path(audio_base_dir) / language_dir / voice / filename

    if not file_path.exists():
        return jsonify({"error": f'Audio file not found: {file_path}'}), 404

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
            next_review = g.db.query(AudioQualityReview).filter(
                AudioQualityReview.id > review_id,
                AudioQualityReview.language_code == review.language_code,
                AudioQualityReview.voice_name == review.voice_name,
                AudioQualityReview.status == "pending_review"
            ).order_by(AudioQualityReview.id).first()

            if next_review:
                return redirect(url_for("audio.review_file", review_id=next_review.id))

        return redirect(url_for("audio.list_files"))

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON for quality_issues"}), 400
    except Exception as e:
        g.db.rollback()
        flash(f'Error updating review: {str(e)}', "error")
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
    language_filter = request.args.get("language", "")
    voice_filter = request.args.get("voice", "")
    status_filter = request.args.get("status", "pending_review")

    # Build query
    query = g.db.query(AudioQualityReview)

    if language_filter:
        query = query.filter(AudioQualityReview.language_code == language_filter)

    if voice_filter:
        query = query.filter(AudioQualityReview.voice_name == voice_filter)

    if status_filter:
        query = query.filter(AudioQualityReview.status == status_filter)

    # Order by GUID
    query = query.order_by(AudioQualityReview.guid)

    # Get total count
    total_count = query.count()

    # Get first file
    current_review = query.first()

    # Get available filter options
    languages = g.db.query(AudioQualityReview.language_code).distinct().all()
    languages = sorted([lang[0] for lang in languages])

    voices = g.db.query(AudioQualityReview.voice_name).distinct().all()
    voices = sorted([voice[0] for voice in voices])

    statuses = ["pending_review", "approved", "approved_with_issues", "needs_replacement"]

    return render_template(
        "audio/rapid_review.html",
        review=current_review,
        total_count=total_count,
        languages=languages,
        voices=voices,
        statuses=statuses,
        language_filter=language_filter,
        voice_filter=voice_filter,
        status_filter=status_filter
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

        # Build query for next file - use GUID ordering, not ID
        # This ensures we get the next file in GUID sequence regardless of ID gaps
        query = g.db.query(AudioQualityReview).filter(AudioQualityReview.guid > review.guid)

        if language_filter:
            query = query.filter(AudioQualityReview.language_code == language_filter)

        if voice_filter:
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

        if status_filter:
            query = query.filter(AudioQualityReview.status == status_filter)

        query = query.order_by(AudioQualityReview.guid)
        next_review = query.first()

        if next_review:
            # Generate pinyin for Chinese text
            pinyin_text = None
            if next_review.language_code == "zh":
                from barsukas.pinyin_helper import generate_pinyin
                pinyin_text = generate_pinyin(next_review.expected_text)

            # Validate audio file against current translation
            validation = validate_audio_translation(
                g.db,
                next_review.guid,
                next_review.expected_text,
                next_review.language_code
            )

            return jsonify({
                "success": True,
                "has_next": True,
                "next_review": {
                    "id": next_review.id,
                    "guid": next_review.guid,
                    "expected_text": next_review.expected_text,
                    "language_code": next_review.language_code,
                    "voice_name": next_review.voice_name,
                    "filename": next_review.filename,
                    "pinyin": pinyin_text,
                    "audio_url": url_for("audio.serve_audio_file",
                                        language=next_review.language_code,
                                        voice=next_review.voice_name,
                                        filename=next_review.filename),
                    "validation": validation
                }
            })
        else:
            return jsonify({
                "success": True,
                "has_next": False,
                "message": "No more files to review"
            })

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

        # Build query for next file - use GUID ordering
        query = g.db.query(AudioQualityReview).filter(AudioQualityReview.guid > review.guid)

        if language_filter:
            query = query.filter(AudioQualityReview.language_code == language_filter)

        if voice_filter:
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

        if status_filter:
            query = query.filter(AudioQualityReview.status == status_filter)

        query = query.order_by(AudioQualityReview.guid)
        next_review = query.first()

        if next_review:
            # Generate pinyin for Chinese text
            pinyin_text = None
            if next_review.language_code == "zh":
                from barsukas.pinyin_helper import generate_pinyin
                pinyin_text = generate_pinyin(next_review.expected_text)

            # Validate audio file against current translation
            validation = validate_audio_translation(
                g.db,
                next_review.guid,
                next_review.expected_text,
                next_review.language_code
            )

            return jsonify({
                "success": True,
                "has_next": True,
                "next_review": {
                    "id": next_review.id,
                    "guid": next_review.guid,
                    "expected_text": next_review.expected_text,
                    "language_code": next_review.language_code,
                    "voice_name": next_review.voice_name,
                    "filename": next_review.filename,
                    "pinyin": pinyin_text,
                    "audio_url": url_for("audio.serve_audio_file",
                                        language=next_review.language_code,
                                        voice=next_review.voice_name,
                                        filename=next_review.filename),
                    "validation": validation
                }
            })
        else:
            return jsonify({
                "success": True,
                "has_next": False,
                "message": "No more files to review"
            })

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

        # Build query for next file - use GUID ordering
        query = g.db.query(AudioQualityReview).filter(AudioQualityReview.guid > review.guid)

        if language_filter:
            query = query.filter(AudioQualityReview.language_code == language_filter)

        if voice_filter:
            query = query.filter(AudioQualityReview.voice_name == voice_filter)

        if status_filter:
            query = query.filter(AudioQualityReview.status == status_filter)

        query = query.order_by(AudioQualityReview.guid)
        next_review = query.first()

        if next_review:
            # Generate pinyin for Chinese text
            pinyin_text = None
            if next_review.language_code == "zh":
                from barsukas.pinyin_helper import generate_pinyin
                pinyin_text = generate_pinyin(next_review.expected_text)

            # Validate audio file against current translation
            validation = validate_audio_translation(
                g.db,
                next_review.guid,
                next_review.expected_text,
                next_review.language_code
            )

            return jsonify({
                "success": True,
                "has_next": True,
                "next_review": {
                    "id": next_review.id,
                    "guid": next_review.guid,
                    "expected_text": next_review.expected_text,
                    "language_code": next_review.language_code,
                    "voice_name": next_review.voice_name,
                    "filename": next_review.filename,
                    "pinyin": pinyin_text,
                    "audio_url": url_for("audio.serve_audio_file",
                                        language=next_review.language_code,
                                        voice=next_review.voice_name,
                                        filename=next_review.filename),
                    "validation": validation
                }
            })
        else:
            return jsonify({
                "success": True,
                "has_next": False,
                "message": "No more files to review"
            })

    except Exception as e:
        g.db.rollback()
        return jsonify({"error": str(e)}), 500
