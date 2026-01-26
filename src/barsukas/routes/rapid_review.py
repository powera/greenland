#!/usr/bin/python3

"""
Rapid Review Routes

Provides streamlined keyboard-driven audio quality review interface.
"""

import json
from datetime import datetime
from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from barsukas.helpers.audio_helpers import validate_audio_translation
from langtools.zh.pinyin_helper import generate_pinyin
from wordfreq.storage.models.schema import AudioQualityReview, Lemma
from wordfreq.storage.queries.lemma import apply_effective_difficulty_filter

bp = Blueprint("rapid_review", __name__, url_prefix="/audio/rapid-review")


@bp.route("/")
def index() -> ResponseReturnValue:
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
    audio_type_filter = request.args.get("type", "")  # "lemma", "sentence", or "" (all)

    # Build query - join with Lemma if we need subtype or level filtering
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

    # Filter by audio type (lemma vs sentence)
    if audio_type_filter == "lemma":
        query = query.filter(AudioQualityReview.sentence_id.is_(None))
    elif audio_type_filter == "sentence":
        query = query.filter(AudioQualityReview.sentence_id.isnot(None))

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

    # Get all filter options in optimized queries (replaces 4 separate DISTINCT queries with 2)
    from barsukas.helpers.db_optimization import get_rapid_review_filter_options

    filter_options = get_rapid_review_filter_options(g.db)
    languages = filter_options["languages"]
    voices = filter_options["voices"]
    subtypes = filter_options["subtypes"]
    levels = filter_options["levels"]

    statuses = ["pending_review", "approved", "approved_with_issues", "needs_replacement"]

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
        audio_type_filter=audio_type_filter,
    )


@bp.route("/submit/<int:review_id>", methods=["POST"])
def submit(review_id: int) -> ResponseReturnValue:
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
        audio_type_filter = data.get("type", "")
        subtype_filter = data.get("subtype", "")
        level_filter = data.get("level", "")

        # Build query for next file - order by (GUID, voice_name) to cycle through all voices
        # Use compound comparison: (guid, voice_name) > (current_guid, current_voice_name)
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

        # Filter by audio type (lemma vs sentence)
        if audio_type_filter == "lemma":
            query = query.filter(AudioQualityReview.sentence_id.is_(None))
        elif audio_type_filter == "sentence":
            query = query.filter(AudioQualityReview.sentence_id.isnot(None))

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


@bp.route("/skip/<int:review_id>", methods=["POST"])
def skip(review_id: int) -> ResponseReturnValue:
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
        audio_type_filter = data.get("type", "")
        subtype_filter = data.get("subtype", "")
        level_filter = data.get("level", "")

        # Build query for next file - order by (GUID, voice_name) to cycle through all voices
        # Use compound comparison: (guid, voice_name) > (current_guid, current_voice_name)
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

        # Filter by audio type (lemma vs sentence)
        if audio_type_filter == "lemma":
            query = query.filter(AudioQualityReview.sentence_id.is_(None))
        elif audio_type_filter == "sentence":
            query = query.filter(AudioQualityReview.sentence_id.isnot(None))

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


@bp.route("/bad-translation/<int:review_id>", methods=["POST"])
def bad_translation(review_id: int) -> ResponseReturnValue:
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
        audio_type_filter = data.get("type", "")
        subtype_filter = data.get("subtype", "")
        level_filter = data.get("level", "")

        # Build query for next file - order by (GUID, voice_name) to cycle through all voices
        # Use compound comparison: (guid, voice_name) > (current_guid, current_voice_name)
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

        # Filter by audio type (lemma vs sentence)
        if audio_type_filter == "lemma":
            query = query.filter(AudioQualityReview.sentence_id.is_(None))
        elif audio_type_filter == "sentence":
            query = query.filter(AudioQualityReview.sentence_id.isnot(None))

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
