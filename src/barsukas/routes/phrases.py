#!/usr/bin/python3

"""Routes for phrase management.

Phrases (fixed traveler/greeting expressions like "See you later") live in their
own ``phrases`` table. This blueprint is the phrase equivalent of
``routes/lemmas.py`` — a list, a detail view, and add/edit/delete — but trimmed,
since phrases have no derivative forms, tiers, embeddings, or grammar facts.
"""

from typing import Any, Dict, List, Optional

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

from barsukas.config import Config
from barsukas.helpers.elements import build_element_rows, group_language_values
from storage.crud.operation_log import log_translation_change
from storage.crud.phrase import (
    add_phrase,
    get_phrase_by_id,
    set_phrase_translation,
)
from storage.models.guid_prefixes import PHRASE_SUBTYPE_GUID_PREFIXES
from storage.models.schema import Phrase, PhraseTranslation
from storage.translation_helpers import get_supported_languages

bp = Blueprint("phrases", __name__, url_prefix="/phrases")


def _available_phrase_subtypes() -> List[str]:
    """Return all known phrase subtypes (union of DB values and known prefixes)."""
    db_subtypes = {r[0] for r in g.db.query(Phrase.phrase_subtype).distinct().all() if r[0]}
    return sorted(db_subtypes | set(PHRASE_SUBTYPE_GUID_PREFIXES.keys()))


def _phrase_translations(phrase_id: int) -> Dict[str, PhraseTranslation]:
    """Return this phrase's translations keyed by language code."""
    rows = g.db.query(PhraseTranslation).filter(PhraseTranslation.phrase_id == phrase_id).all()
    return {row.language_code: row for row in rows}


@bp.route("/")
def list_phrases() -> ResponseReturnValue:
    """List phrases, optionally filtered by subtype."""
    subtype = request.args.get("subtype", "").strip()
    page = request.args.get("page", 1, type=int)

    query = g.db.query(Phrase)
    if subtype:
        query = query.filter(Phrase.phrase_subtype == subtype)
    query = query.order_by(Phrase.guid, Phrase.id)

    total = query.count()
    total_pages = max(1, (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))
    phrases = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    rows = build_element_rows(
        phrases,
        {phrase.id: url_for("phrases.view_phrase", phrase_id=phrase.id) for phrase in phrases},
    )

    return render_template(
        "phrases/list.html",
        rows=rows,
        subtype_by_id={phrase.id: phrase.phrase_subtype for phrase in phrases},
        subtype=subtype,
        subtypes=_available_phrase_subtypes(),
        page=page,
        total=total,
        total_pages=total_pages,
    )


@bp.route("/<int:phrase_id>")
def view_phrase(phrase_id: int) -> ResponseReturnValue:
    """View a single phrase with its translations."""
    phrase = get_phrase_by_id(g.db, phrase_id)
    if not phrase:
        flash("Phrase not found", "error")
        return redirect(url_for("phrases.list_phrases"))

    return render_template(
        "phrases/view.html",
        phrase=phrase,
        values_by_language=group_language_values(phrase.language_values),
        language_names=get_supported_languages(),
    )


@bp.route("/add", methods=["GET", "POST"])
def add_phrase_route() -> ResponseReturnValue:
    """Create a new phrase."""
    if request.method == "POST":
        if current_app.config.get("READONLY", False):
            flash("Cannot add: running in read-only mode", "error")
            return redirect(url_for("phrases.list_phrases"))

        phrase_subtype = request.form.get("phrase_subtype", "").strip()
        label = request.form.get("label", "").strip()
        definition = request.form.get("definition", "").strip() or None
        english = request.form.get("english", "").strip()

        if not phrase_subtype or not label:
            flash("Phrase subtype and label are required", "error")
            return redirect(url_for("phrases.add_phrase_route"))

        difficulty_level = _parse_difficulty(request.form.get("difficulty_level", "").strip())

        phrase = add_phrase(
            g.db,
            phrase_subtype=phrase_subtype,
            label=label,
            definition=definition,
            difficulty_level=difficulty_level,
        )
        # The English translation defaults to the label if not supplied.
        set_phrase_translation(g.db, phrase, "en", english or label)
        g.db.commit()
        flash(f"Created phrase: {phrase.label} ({phrase.guid})", "success")
        return redirect(url_for("phrases.view_phrase", phrase_id=phrase.id))

    return render_template(
        "phrases/add.html",
        subtypes=_available_phrase_subtypes(),
    )


@bp.route("/<int:phrase_id>/edit", methods=["GET", "POST"])
def edit_phrase(phrase_id: int) -> ResponseReturnValue:
    """Edit a phrase's metadata and translations."""
    phrase = g.db.query(Phrase).get(phrase_id)
    if not phrase:
        flash("Phrase not found", "error")
        return redirect(url_for("phrases.list_phrases"))

    if request.method == "POST":
        if current_app.config.get("READONLY", False):
            flash("Cannot update: running in read-only mode", "error")
            return redirect(url_for("phrases.view_phrase", phrase_id=phrase_id))

        new_label = request.form.get("label", "").strip()
        if new_label and new_label != phrase.label:
            _log(phrase_id, "label", phrase.label, new_label)
            phrase.label = new_label

        new_definition = request.form.get("definition", "").strip() or None
        if new_definition != phrase.definition:
            _log(phrase_id, "definition", phrase.definition, new_definition)
            phrase.definition = new_definition

        new_subtype = request.form.get("phrase_subtype", "").strip()
        if new_subtype and new_subtype != phrase.phrase_subtype:
            _log(phrase_id, "phrase_subtype", phrase.phrase_subtype, new_subtype)
            phrase.phrase_subtype = new_subtype

        new_guid = request.form.get("guid", "").strip() or None
        if new_guid != phrase.guid:
            _log(phrase_id, "guid", phrase.guid, new_guid)
            phrase.guid = new_guid

        new_difficulty = _parse_difficulty(request.form.get("difficulty_level", "").strip())
        if new_difficulty != phrase.difficulty_level:
            _log(phrase_id, "difficulty_level", phrase.difficulty_level, new_difficulty)
            phrase.difficulty_level = new_difficulty

        new_verified = request.form.get("verified") == "on"
        if new_verified != phrase.verified:
            _log(phrase_id, "verified", phrase.verified, new_verified)
            phrase.verified = new_verified

        new_notes = request.form.get("notes", "").strip() or None
        if new_notes != phrase.notes:
            _log(phrase_id, "notes", phrase.notes, new_notes)
            phrase.notes = new_notes

        # Update translations from the per-language text inputs.
        existing = _phrase_translations(phrase_id)
        for lang_code in get_supported_languages():
            field_value = request.form.get(f"translation_{lang_code}")
            if field_value is None:
                continue
            field_value = field_value.strip()
            current = existing.get(lang_code)
            current_text = current.translation if current else ""
            if field_value == current_text:
                continue
            if field_value:
                set_phrase_translation(g.db, phrase, lang_code, field_value)
            elif current is not None:
                g.db.delete(current)

        g.db.commit()
        flash(f"Updated phrase: {phrase.label}", "success")
        return redirect(url_for("phrases.view_phrase", phrase_id=phrase.id))

    return render_template(
        "phrases/edit.html",
        phrase=phrase,
        translations=_phrase_translations(phrase_id),
        language_names=get_supported_languages(),
        subtypes=_available_phrase_subtypes(),
    )


@bp.route("/<int:phrase_id>/delete", methods=["POST"])
def delete_phrase(phrase_id: int) -> ResponseReturnValue:
    """Delete a phrase (and its translations via cascade)."""
    if current_app.config.get("READONLY", False):
        flash("Cannot delete: running in read-only mode", "error")
        return redirect(url_for("phrases.view_phrase", phrase_id=phrase_id))

    phrase = g.db.query(Phrase).get(phrase_id)
    if not phrase:
        flash("Phrase not found", "error")
        return redirect(url_for("phrases.list_phrases"))

    label = phrase.label
    _log(phrase_id, "delete", phrase.guid, None)
    g.db.delete(phrase)
    g.db.commit()
    flash(f"Deleted phrase: {label}", "success")
    return redirect(url_for("phrases.list_phrases"))


def _parse_difficulty(value: str) -> Optional[int]:
    """Parse a difficulty-level form value into an int, or None if blank/invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _log(phrase_id: int, field_name: str, old_value: Any, new_value: Any) -> None:
    """Record a phrase field change in the operation log."""
    log_translation_change(
        session=g.db,
        source=Config.OPERATION_LOG_SOURCE,
        operation_type="phrase_update",
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
    )
