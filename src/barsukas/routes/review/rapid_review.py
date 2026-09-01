#!/usr/bin/python3

"""
Rapid Review Routes

Provides streamlined keyboard-driven audio quality review interface.
"""

import json
import logging
from datetime import datetime
from typing import Optional

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

from barsukas.helpers.audio_helpers import sync_rejection_to_s3, validate_audio_translation
from langtools.zh.pinyin_helper import generate_pinyin
from storage.models.schema import AudioQualityReview, Lemma, Sentence, SentenceTranslation
from storage.queries.lemma import apply_effective_difficulty_filter

bp = Blueprint("rapid_review", __name__, url_prefix="/audio/rapid-review")


def get_english_translation_for_review(review: AudioQualityReview) -> Optional[str]:
    """Get the English translation for a sentence audio review."""
    if not review.sentence_id:
        return None
    # Query for the English translation of this sentence
    translation = (
        g.db.query(SentenceTranslation)
        .filter(
            SentenceTranslation.sentence_id == review.sentence_id,
            SentenceTranslation.language_code == "en",
        )
        .first()
    )
    return translation.translation_text if translation else None


@bp.route("/")
def index() -> ResponseReturnValue:
    """Streamlined rapid review interface with keyboard shortcuts."""
    # Get filter parameters - default to pending_review
    # Language is REQUIRED - redirect to list if not provided
    language_filter = request.args.get("language", "")
    if not language_filter:
        flash("Please select a language to begin rapid review", "warning")
        return redirect(url_for("audio.index"))

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
        # Exclude rejected sentences from sentence audio review
        query = query.join(Sentence, AudioQualityReview.sentence_id == Sentence.id)
        query = query.filter(Sentence.rejected == False)

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

    # Get English translation for sentence audio
    english_translation = None
    if current_review:
        english_translation = get_english_translation_for_review(current_review)

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
        english_translation=english_translation,
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

        # If approved, also push to production
        if status in ["approved", "approved_with_issues"]:
            if review.s3_staging_url and not review.s3_prod_url:
                from barsukas.helpers.audio_helpers import copy_staging_to_prod

                success, prod_url = copy_staging_to_prod(review.s3_staging_url)
                if success:
                    review.s3_prod_url = prod_url
                    review.accepted_at = datetime.utcnow()
                    review.accepted_by = "rapid_review"
                else:
                    # Log but don't fail the review - audio can be pushed later
                    logging.getLogger(__name__).warning(
                        f"Failed to push audio {review_id} to production: {prod_url}"
                    )

        # Publish the verdict into the staged manifest so every database that
        # imports this audio honors it, not just this one. Driven by the new
        # status, so an undo back to pending_review clears the block the
        # rejection wrote. Failure is non-fatal: the database verdict stands and
        # scripts/push_audio_rejections_to_s3.py reconciles later.
        synced, sync_message = sync_rejection_to_s3(review)
        if not synced:
            logging.getLogger(__name__).warning(
                f"Failed to sync rejection state for audio {review_id}: {sync_message}"
            )

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
            # Exclude rejected sentences from sentence audio review
            query = query.join(Sentence, AudioQualityReview.sentence_id == Sentence.id)
            query = query.filter(Sentence.rejected == False)

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

            # Get English translation for sentence audio
            english_translation = get_english_translation_for_review(next_review)

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
                        "english_translation": english_translation,
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
            # Exclude rejected sentences from sentence audio review
            query = query.join(Sentence, AudioQualityReview.sentence_id == Sentence.id)
            query = query.filter(Sentence.rejected == False)

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

            # Get English translation for sentence audio
            english_translation = get_english_translation_for_review(next_review)

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
                        "english_translation": english_translation,
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

        # Publish the rejection, as the reject button does. The text being wrong
        # still makes this recording bad: the corrected text is re-recorded as a
        # new file with its own MD5 and manifest, so rejecting this one is right.
        synced, sync_message = sync_rejection_to_s3(review)
        if not synced:
            logging.getLogger(__name__).warning(
                f"Failed to sync rejection state for audio {review_id}: {sync_message}"
            )

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
            # Exclude rejected sentences from sentence audio review
            query = query.join(Sentence, AudioQualityReview.sentence_id == Sentence.id)
            query = query.filter(Sentence.rejected == False)

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

            # Get English translation for sentence audio
            english_translation = get_english_translation_for_review(next_review)

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
                        "english_translation": english_translation,
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
