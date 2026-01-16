#!/usr/bin/python3

"""
Audio Quality Review Routes

Provides routes for managing and reviewing audio file quality.
"""

import io
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from agents.strazdas import StrazdasAgent
from agents.vieversys import VieversysAgent
from audioshoe.coqui import CoquiClient, CoquiVoice
from audioshoe.espeak import EspeakVoice
from audioshoe.piper import PiperClient, PiperVoice
from barsukas.helpers.audio_helpers import link_audio_to_lemma, validate_audio_translation
from clients.audio import Voice
import constants
from wordfreq.storage.models.schema import AudioQualityReview, Lemma, LemmaDifficultyOverride
from wordfreq.storage.queries.lemma import apply_effective_difficulty_filter

bp = Blueprint("audio", __name__, url_prefix="/audio")
logger = logging.getLogger(__name__)


@bp.route("/")
def index() -> ResponseReturnValue:
    """Audio quality review dashboard."""
    from barsukas.helpers.db_optimization import get_audio_dashboard_stats

    # Get all stats in optimized queries (replaces 6 separate queries with 2)
    stats = get_audio_dashboard_stats(g.db)

    return render_template(
        "audio/index.html",
        total_files=stats["total_files"],
        pending_review=stats["pending_review"],
        approved=stats["approved"],
        needs_replacement=stats["needs_replacement"],
        language_counts=stats["language_counts"],
        voice_counts=stats["voice_counts"],
    )


@bp.route("/import", methods=["GET", "POST"])
def import_manifest() -> ResponseReturnValue:
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
                    # Note: Not setting S3 URLs from manifest imports.
                    # Use audio generation agents with --upload-s3 flag instead.
                    updated_count += 1
                else:
                    unchanged_count += 1
                continue

            # Try to link to lemma
            lemma_id = link_audio_to_lemma(g.db, guid, text, language_code)

            # Create new review record
            # Note: S3 URLs are not set from manifest imports.
            # Use audio generation agents with --upload-s3 flag to populate S3 fields.
            review = AudioQualityReview(
                guid=guid,
                sentence_id=None,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=grammatical_form,
                filename=filename,
                expected_text=text,
                manifest_md5=md5,
                s3_staging_url=None,
                s3_staging_manifest_url=None,
                s3_prod_url=None,
                staging_agent=None,
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
def list_files() -> ResponseReturnValue:
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
def download_filelist() -> ResponseReturnValue:
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
        # Use language code directly as directory name (e.g., 'zh', 'lt')
        # The audio directory structure uses language codes, not full names
        file_path = Path(audio_base_dir) / file.language_code / file.voice_name / file.filename

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
def serve_audio_file(language: str, voice: str, filename: str) -> ResponseReturnValue:
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

    # Priority order: prod URL > staging URL > local file
    if review:
        # First check for production URL (highest priority)
        if review.s3_prod_url:
            return redirect(review.s3_prod_url)

        # Then check for staging URL (for review purposes)
        if review.s3_staging_url:
            return redirect(review.s3_staging_url)

    # Fallback to local file serving
    audio_base_dir = current_app.config.get("AUDIO_BASE_DIR")

    if not audio_base_dir:
        return jsonify({"error": "Audio directory not configured and no S3 URL available"}), 500

    # Try language code directory first (new structure: e.g., 'lt', 'zh')
    file_path = Path(audio_base_dir) / language / voice / filename

    # If not found, try legacy language name directory (e.g., 'lithuanian', 'chinese')
    if not file_path.exists():
        from wordfreq.storage.translation_helpers import LANGUAGE_NAMES

        legacy_name = LANGUAGE_NAMES.get(language, language).lower()
        file_path = Path(audio_base_dir) / legacy_name / voice / filename

    logger.info(f"Serving audio file: {file_path} (exists: {file_path.exists()})")

    if not file_path.exists():
        return jsonify({"error": f"Audio file not found locally: {file_path}"}), 404

    return send_file(str(file_path), mimetype="audio/mpeg")


@bp.route("/review/<int:review_id>", methods=["GET", "POST"])
def review_file(review_id: int) -> ResponseReturnValue:
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

        # Fetch raw manifest if available
        raw_manifest = None
        if review.s3_staging_manifest_url:
            try:
                import requests

                response = requests.get(review.s3_staging_manifest_url, timeout=5)
                if response.status_code == 200:
                    raw_manifest = response.json()
            except Exception as e:
                logger.warning(
                    f"Failed to fetch manifest from {review.s3_staging_manifest_url}: {e}"
                )

        return render_template(
            "audio/review.html", review=review, lemma=lemma, raw_manifest=raw_manifest
        )

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
def quick_update(review_id: int) -> ResponseReturnValue:
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


@bp.route("/remove/<int:review_id>", methods=["POST"])
def remove_file(review_id: int) -> ResponseReturnValue:
    """Remove an audio file review record."""
    review = g.db.query(AudioQualityReview).filter_by(id=review_id).first()

    if not review:
        flash("Audio review not found", "error")
        return redirect(url_for("audio.list_files"))

    try:
        g.db.delete(review)
        g.db.commit()
        flash("Audio file record removed successfully", "success")
        return redirect(url_for("audio.list_files"))
    except Exception as e:
        g.db.rollback()
        flash(f"Error removing audio file: {str(e)}", "error")
        return redirect(url_for("audio.review_file", review_id=review_id))


@bp.route("/accept/<int:review_id>", methods=["POST"])
def accept_for_production(review_id: int) -> ResponseReturnValue:
    """Accept an audio file for production by moving it from staging to prod."""
    from clients.audio.audio_acceptance import accept_audio_for_production

    review = g.db.query(AudioQualityReview).filter_by(id=review_id).first()

    if not review:
        flash("Audio review not found", "error")
        return redirect(url_for("audio.list_files"))

    # Check if already in production
    if review.s3_prod_url:
        flash("Audio is already in production", "info")
        return redirect(url_for("audio.review_file", review_id=review_id))

    # Check if in staging
    if not review.s3_staging_url:
        flash("Audio must be in staging before it can be accepted for production", "error")
        return redirect(url_for("audio.review_file", review_id=review_id))

    try:
        # Accept audio for production
        success, message = accept_audio_for_production(
            session=g.db,
            audio_review_id=review_id,
            accepted_by=session.get(
                "username", "unknown"
            ),  # Get username from session if available
        )

        if success:
            flash(f"Audio accepted for production: {message}", "success")
        else:
            flash(f"Failed to accept audio: {message}", "error")

        return redirect(url_for("audio.review_file", review_id=review_id))
    except Exception as e:
        logger.error(f"Error accepting audio: {e}")
        flash(f"Error accepting audio: {str(e)}", "error")
        return redirect(url_for("audio.review_file", review_id=review_id))


@bp.route("/accept-bulk", methods=["POST"])
def accept_bulk_production() -> ResponseReturnValue:
    """Accept multiple audio files for production."""
    from clients.audio.audio_acceptance import accept_multiple_audio

    # Get list of IDs from form
    review_ids = request.form.getlist("review_ids", type=int)

    if not review_ids:
        flash("No audio files selected", "error")
        return redirect(url_for("audio.list_files"))

    try:
        success_count, failure_count, error_messages = accept_multiple_audio(
            session=g.db,
            audio_review_ids=review_ids,
            accepted_by=session.get("username", "unknown"),
        )

        if success_count > 0:
            flash(f"Successfully accepted {success_count} audio file(s) for production", "success")

        if failure_count > 0:
            flash(
                f"Failed to accept {failure_count} audio file(s). Errors: {'; '.join(error_messages[:5])}",
                "error",
            )

        return redirect(url_for("audio.list_files"))
    except Exception as e:
        logger.error(f"Error bulk accepting audio: {e}")
        flash(f"Error bulk accepting audio: {str(e)}", "error")
        return redirect(url_for("audio.list_files"))


# ============================================================================
# Audio Generation Routes
# ============================================================================


@bp.route("/generate", methods=["GET", "POST"])
def generate() -> ResponseReturnValue:
    """Audio generation interface."""
    if request.method == "GET":
        # Show generation form
        supported_languages = ["lt", "zh", "ko", "fr", "de", "es", "pt", "sw", "vi"]

        # OpenAI voices
        openai_voices = [
            "ash",
            "alloy",
            "nova",
            "ballad",
            "coral",
            "echo",
            "fable",
            "onyx",
            "sage",
            "shimmer",
        ]

        # eSpeak-NG voices by language
        espeak_voices = {}
        for lang in supported_languages:
            voices = EspeakVoice.get_voices_for_language(lang)
            espeak_voices[lang] = [{"name": v.name, "gender": v.gender} for v in voices]

        tts_engines = ["openai", "espeak-ng"]

        return render_template(
            "audio/generate.html",
            supported_languages=supported_languages,
            openai_voices=openai_voices,
            espeak_voices=espeak_voices,
            tts_engines=tts_engines,
        )

    # Handle POST - trigger generation
    language_code = request.form.get("language")
    limit = request.form.get("limit", type=int)
    difficulty_level = request.form.get("difficulty_level", type=int)
    voice_names: List[str] = request.form.getlist("voices")
    tts_engine = request.form.get("tts_engine", "openai")
    use_ipa = request.form.get("use_ipa") == "on"

    if not language_code:
        flash("Language is required", "error")
        return redirect(url_for("audio.generate"))

    if not voice_names:
        flash("At least one voice must be selected", "error")
        return redirect(url_for("audio.generate"))

    # Convert voice names to appropriate enums based on TTS engine
    try:
        if tts_engine == "espeak-ng":
            # Convert to EspeakVoice enums
            espeak_voice_enums = [EspeakVoice[v.upper()] for v in voice_names]
        else:
            # Convert to OpenAI Voice enums
            openai_voice_enums = [Voice(v) for v in voice_names]
    except (ValueError, KeyError) as e:
        flash(f"Invalid voice: {e}", "error")
        return redirect(url_for("audio.generate"))

    # Run the appropriate agent based on TTS engine
    try:
        # Use AUDIO_BASE_DIR for persistent storage
        audio_base_dir = current_app.config.get("AUDIO_BASE_DIR")
        if not audio_base_dir:
            audio_base_dir = Path(tempfile.mkdtemp(prefix="audio_gen_"))
        else:
            audio_base_dir = Path(audio_base_dir)

        # Create DataSourceConfig for agents
        from config import Config

        from wordfreq.storage.backend.config import BackendType, DataSourceConfig

        config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )

        if tts_engine == "espeak-ng":
            strazdas_agent = StrazdasAgent(config=config, output_dir=str(audio_base_dir))
            results = strazdas_agent.generate_batch(
                language_code=language_code,
                voices=espeak_voice_enums,
                use_ipa=use_ipa,
            )
            engine_name = "eSpeak-NG"
        else:
            vieversys_agent = VieversysAgent(config=config, output_dir=str(audio_base_dir))
            results = vieversys_agent.generate_batch(
                language_code=language_code,
                voices=openai_voice_enums,
            )
            engine_name = "OpenAI"

        flash(
            f"Generated audio using {engine_name} for {results['success_count']} lemmas "
            f"({results['error_count']} errors). "
            f"Files saved to {audio_base_dir}",
            "success" if results["error_count"] == 0 else "warning",
        )

        return redirect(
            url_for("audio.list_files", language=language_code, status="pending_review")
        )

    except Exception as e:
        flash(f"Error generating audio: {str(e)}", "error")
        return redirect(url_for("audio.generate"))


def _generate_audio_piper(
    session: Any, lemma: Lemma, language_code: str, voices: list, output_dir: str
) -> Dict[str, Any]:
    """
    Generate audio for a lemma using Piper TTS.

    Args:
        session: Database session
        lemma: Lemma object
        language_code: Language code (e.g., "lt", "zh")
        voices: List of PiperVoice enums
        output_dir: Base output directory

    Returns:
        dict with success, voices, and error information
    """
    import hashlib

    from clients.audio.types import AudioFormat
    from wordfreq.storage.translation_helpers import get_translation

    try:
        # Get translation for the language
        translation = get_translation(session, lemma, language_code)
        if not translation:
            return {
                "success": False,
                "error": f"No translation found for language: {language_code}",
            }

        # Create Piper client
        client = PiperClient()

        # Generate audio for each voice
        generated_voices = []
        for voice in voices:
            # Generate audio
            result = client.generate_audio(
                text=translation,
                voice=voice,
                audio_format=AudioFormat.MP3,
                speed=1.0,
            )

            if not result.success:
                logger.error(f"Failed to generate audio for {voice.ui_name}: {result.error}")
                continue

            # Save audio file
            voice_dir = Path(output_dir) / language_code / voice.ui_name
            voice_dir.mkdir(parents=True, exist_ok=True)

            # Calculate MD5 hash
            md5_hash = hashlib.md5(result.audio_data).hexdigest()
            filename = f"{md5_hash}.mp3"
            file_path = voice_dir / filename

            with open(file_path, "wb") as f:
                f.write(result.audio_data)

            # Create review record
            review = AudioQualityReview(
                guid=lemma.guid,
                lemma_id=lemma.id,
                language_code=language_code,
                voice_name=voice.ui_name,
                filename=filename,
                expected_text=translation,
                manifest_md5=md5_hash,
                status="pending_review",
                quality_issues=json.dumps([]),
            )
            session.add(review)
            generated_voices.append(voice.ui_name)

        session.commit()

        return {
            "success": True,
            "voices": generated_voices,
        }

    except Exception as e:
        logger.error(f"Error generating Piper audio: {e}")
        return {"success": False, "error": str(e)}


def _generate_audio_coqui(
    session: Any, lemma: Lemma, language_code: str, voices: list, output_dir: str
) -> Dict[str, Any]:
    """
    Generate audio for a lemma using Coqui TTS.

    Args:
        session: Database session
        lemma: Lemma object
        language_code: Language code (e.g., "lt", "zh")
        voices: List of CoquiVoice enums
        output_dir: Base output directory

    Returns:
        dict with success, voices, and error information
    """
    import hashlib

    from clients.audio.types import AudioFormat
    from wordfreq.storage.translation_helpers import get_translation

    try:
        # Get translation for the language
        translation = get_translation(session, lemma, language_code)
        if not translation:
            return {
                "success": False,
                "error": f"No translation found for language: {language_code}",
            }

        # Create Coqui client
        client = CoquiClient()

        # Generate audio for each voice
        generated_voices = []
        for voice in voices:
            # Generate audio
            result = client.generate_audio(
                text=translation,
                voice=voice,
                audio_format=AudioFormat.MP3,
                speed=1.0,
            )

            if not result.success:
                logger.error(f"Failed to generate audio for {voice.ui_name}: {result.error}")
                continue

            # Save audio file
            voice_dir = Path(output_dir) / language_code / voice.ui_name
            voice_dir.mkdir(parents=True, exist_ok=True)

            # Calculate MD5 hash
            md5_hash = hashlib.md5(result.audio_data).hexdigest()
            filename = f"{md5_hash}.mp3"
            file_path = voice_dir / filename

            with open(file_path, "wb") as f:
                f.write(result.audio_data)

            # Create review record
            review = AudioQualityReview(
                guid=lemma.guid,
                lemma_id=lemma.id,
                language_code=language_code,
                voice_name=voice.ui_name,
                filename=filename,
                expected_text=translation,
                manifest_md5=md5_hash,
                status="pending_review",
                quality_issues=json.dumps([]),
            )
            session.add(review)
            generated_voices.append(voice.ui_name)

        session.commit()

        return {
            "success": True,
            "voices": generated_voices,
        }

    except Exception as e:
        logger.error(f"Error generating Coqui audio: {e}")
        return {"success": False, "error": str(e)}


@bp.route("/generate-single/<guid>", methods=["POST"])
def generate_single(guid: str) -> ResponseReturnValue:
    """Generate audio for a single lemma (queued via task worker)."""
    from barsukas.utils.task_queue import TaskType, enqueue_task

    # Support both JSON and form data
    if request.is_json:
        data = request.get_json()
        language_code = data.get("language")
        voices = data.get("voices", ["ash", "alloy", "nova"])
        tts_engine = data.get("tts_engine", "openai")
        use_ipa = data.get("use_ipa", False)
    else:
        language_code = request.form.get("language")
        voices = request.form.getlist("voices")
        if not voices:
            voices = ["ash", "alloy", "nova"]
        tts_engine = request.form.get("tts_engine", "openai")
        use_ipa = request.form.get("use_ipa") == "on"

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
        # Enqueue audio generation task
        result = enqueue_task(
            g.db,
            task_type=TaskType.GENERATE_AUDIO,
            target_type="lemma",
            target_id=lemma.id,
            payload={
                "lemma_id": lemma.id,
                "language_code": language_code,
                "voices": voices,
                "tts_engine": tts_engine,
                "use_ipa": use_ipa,
            },
            dedup_key=f"{TaskType.GENERATE_AUDIO}:{lemma.id}:{language_code}:{tts_engine}",
        )

        if request.is_json:
            if result.created:
                return jsonify(
                    {
                        "success": True,
                        "queued": True,
                        "task_id": result.task.id,
                        "guid": guid,
                        "language": language_code,
                        "message": "Audio generation queued. A worker will process it shortly.",
                    }
                )
            else:
                return jsonify(
                    {
                        "success": True,
                        "queued": False,
                        "task_id": result.task.id,
                        "message": "Audio generation already in progress for this lemma/language.",
                    }
                )
        else:
            if result.created:
                flash(
                    f"Queued audio generation for {language_code}. A worker will process it shortly.",
                    "info",
                )
            else:
                flash(
                    "Audio generation already in progress for this lemma/language.",
                    "warning",
                )
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma.id))

    except Exception as e:
        logger.exception("Error enqueueing audio generation task")
        if request.is_json:
            return jsonify({"error": str(e)}), 500
        else:
            flash(f"Error queuing audio generation: {str(e)}", "error")
            return redirect(url_for("lemmas.view_lemma", lemma_id=lemma.id))
