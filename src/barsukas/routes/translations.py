#!/usr/bin/python3
# MIRROR NOTICE: If you edit this route module, update the matching wrapper in top-level api/ in the same commit.

"""Routes for translation management."""

from typing import Union

from barsukas.config import Config
from flask import Blueprint, flash, g, jsonify, redirect, request, url_for
from werkzeug.wrappers import Response

from storage.crud.operation_log import log_translation_change
from storage.models.schema import Lemma
from storage.translation_helpers import (
    get_supported_languages,
    get_translation,
    set_translation,
    set_translation_disambiguation,
)

bp = Blueprint("translations", __name__, url_prefix="/translations")


@bp.route("/<int:lemma_id>/<lang_code>", methods=["POST"])
def update_translation(lemma_id: int, lang_code: str) -> Response:
    """Update a translation for a lemma."""
    from flask import current_app

    if current_app.config.get("READONLY", False):
        flash("Cannot update: running in read-only mode", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    lemma = g.db.query(Lemma).get(lemma_id)
    if not lemma:
        flash("Lemma not found", "error")
        return redirect(url_for("lemmas.list_lemmas"))

    # Validate language code
    if lang_code not in get_supported_languages():
        flash("Invalid language code", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Get new translation value and optional return_to parameter
    new_translation = request.form.get("translation", "").strip()
    new_disambiguation = request.form.get("disambiguation", "").strip() or None
    return_to = request.form.get("return_to", "").strip()

    if not new_translation:
        flash("Translation cannot be empty", "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Check for slash warning (will be shown in UI, but we allow it)
    has_slash = "/" in new_translation

    try:
        # Update translation using helper
        old_translation, new_translation = set_translation(g.db, lemma, lang_code, new_translation)

        # Update disambiguation if provided (non-English languages only)
        if lang_code != "en":
            set_translation_disambiguation(g.db, lemma, lang_code, new_disambiguation)

        # Log the change
        log_translation_change(
            session=g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type="translation",
            lemma_id=lemma.id,
            language_code=lang_code,
            old_translation=old_translation,
            new_translation=new_translation,
        )

        g.db.commit()

        # Flash message with warning if needed
        message = f"Updated {get_supported_languages()[lang_code]} translation"
        if has_slash:
            message += ' (note: contains "/")'
            flash(message, "warning")
        else:
            flash(message, "success")

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))

    # Redirect based on return_to parameter
    if return_to == "check_translations":
        return redirect(url_for("agents.check_translations", lemma_id=lemma_id))
    else:
        return redirect(url_for("lemmas.view_lemma", lemma_id=lemma_id))


@bp.route("/<int:lemma_id>/<lang_code>/check", methods=["GET"])
def check_translation(lemma_id: int, lang_code: str) -> Response:
    """Check if a translation has a slash (for AJAX validation)."""
    translation = request.args.get("translation", "")
    has_slash = "/" in translation
    return jsonify({"has_slash": has_slash})
