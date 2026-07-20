#!/usr/bin/python3

"""Routes for syncing lemma audio between release files and the DB.

Lemma audio metadata (not the mp3 bytes) lives beside the lemma release records::

    data/release/lemmas/{pos_dir}/{pos_subtype}/audio.jsonl

Each line is one GUID with an ``audio`` array of per-(language, voice) records
carrying the S3 URLs and review status. Only audio in an approved status is
exported. Unlike the other sync pages there is no per-word editing workflow here:
lemma audio is a bulk mirror keyed on ``(guid, language_code, voice_name,
grammatical_form)``, so this page exposes whole-directory Import / Export actions
plus a read-only diff summary. Sentence audio is synced separately via
``sync_sentence_release``.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue

from storage.migrate import (
    export_lemma_audio_release_from_session,
    import_lemma_audio_release_into_session,
    summarize_lemma_audio_release_diff,
)

if TYPE_CHECKING:
    from barsukas.app import BarsukasFlask

logger = logging.getLogger(__name__)

bp = Blueprint("sync_lemma_audio_release", __name__, url_prefix="/sync/lemma-audio")

DEFAULT_RELEASE_DIR = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "release" / "lemmas"
)


def _get_release_dir() -> Path:
    return DEFAULT_RELEASE_DIR


@bp.route("/")
def index() -> ResponseReturnValue:
    """Landing page: diff summary and Import / Export actions for lemma audio."""
    release_dir = _get_release_dir()
    diff = summarize_lemma_audio_release_diff(g.db, str(release_dir))
    return render_template(
        "sync_lemma_audio_release/index.html",
        release_dir=str(release_dir),
        diff=diff,
    )


@bp.route("/import", methods=["POST"])
def import_release() -> ResponseReturnValue:
    """Sync approved lemma audio from the release files into the database."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    release_dir = _get_release_dir()
    prune = request.form.get("prune") == "on"

    try:
        stats = import_lemma_audio_release_into_session(g.db, str(release_dir), prune=prune)
    except Exception as e:  # noqa: BLE001 - surface the failure to the user
        g.db.rollback()
        logger.error(f"Lemma audio import failed: {e}")
        flash(f"Import failed: {e}", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    message = f"Imported lemma audio: {stats.added} added, {stats.updated} updated"
    if prune:
        message += f", {stats.pruned} pruned"
    flash(message + ".", "success")
    return redirect(url_for("sync_lemma_audio_release.index"))


@bp.route("/export", methods=["POST"])
def export_release() -> ResponseReturnValue:
    """Export approved lemma audio from the database to the release files."""
    app: "BarsukasFlask" = current_app  # type: ignore[assignment]
    if app.config.get("READONLY", False):
        flash("Database is in read-only mode", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    release_dir = _get_release_dir()

    try:
        stats = export_lemma_audio_release_from_session(g.db, str(release_dir))
    except Exception as e:  # noqa: BLE001 - surface the failure to the user
        logger.error(f"Lemma audio export failed: {e}")
        flash(f"Export failed: {e}", "error")
        return redirect(url_for("sync_lemma_audio_release.index"))

    flash(
        f"Exported {stats.audio_rows} audio row(s) across "
        f"{stats.guids} GUID(s) in {stats.categories} categor"
        f"{'y' if stats.categories == 1 else 'ies'}.",
        "success",
    )
    return redirect(url_for("sync_lemma_audio_release.index"))
