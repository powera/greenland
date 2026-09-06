#!/usr/bin/python3

"""Routes for the names registry.

Names are the third kind of entry beside lemmas and concepts: proper names our
texts use ("George", "Fresh Mart") that are not vocabulary and are not
encyclopedia topics. See ``storage/models/name_entity.py``.

This section exists mostly so the renderings can be curated: a name is only
useful to the translation and audio pipelines once someone has said how it is
written in Lithuanian, Chinese, and the rest.
"""

import logging
from typing import Union

from barsukas.config import Config
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from werkzeug.wrappers import Response

from barsukas.helpers.flash_helpers import flash_and_log
from storage.crud.name_entity import (
    count_names,
    create_name,
    delete_name,
    get_name_by_id,
    get_name_renderings,
    list_names,
    set_name_translation,
    update_name,
)
from storage.models.name_entity import (
    DEFAULT_RENDERING_KIND,
    NAME_GENDERS,
    NAME_KIND_LABELS,
    NAME_KINDS,
    RENDERING_KIND_LABELS,
    RENDERING_KINDS,
    NameTranslation,
)
from storage.models.schema import SentenceWord
from storage.translation_helpers import get_supported_languages

logger = logging.getLogger(__name__)

bp = Blueprint("names", __name__, url_prefix="/names")


def _is_readonly() -> bool:
    """True when the app is running against a read-only database."""
    return bool(current_app.config.get("READONLY"))


@bp.route("/")
def list_names_view() -> ResponseReturnValue:
    """List registered names with pagination and filtering."""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    kind = request.args.get("kind", "").strip()

    total = count_names(g.db, kind=kind or None, search=search or None)
    names = list_names(
        g.db,
        kind=kind or None,
        search=search or None,
        limit=Config.ITEMS_PER_PAGE,
        offset=(page - 1) * Config.ITEMS_PER_PAGE,
    )

    rendering_counts = {name.id: len(name.translations) for name in names}
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "names/list.html",
        names=names,
        rendering_counts=rendering_counts,
        total=total,
        page=page,
        total_pages=total_pages,
        search=search,
        kind=kind,
        name_kinds=NAME_KINDS,
        name_kind_labels=NAME_KIND_LABELS,
    )


@bp.route("/create", methods=["POST"])
def create() -> Response:
    """Create a name by hand."""
    if _is_readonly():
        flash("Cannot create names in read-only mode", "error")
        return redirect(url_for("names.list_names_view"))

    try:
        name = create_name(
            g.db,
            name_text=request.form.get("name_text", ""),
            kind=request.form.get("kind", "given_name"),
            disambiguation=request.form.get("disambiguation", "").strip() or None,
            gender=request.form.get("gender", "").strip() or None,
            verified=True,
            source=Config.OPERATION_LOG_SOURCE,
        )
        g.db.commit()
    except ValueError as exc:
        g.db.rollback()
        flash(str(exc), "error")
        return redirect(url_for("names.list_names_view"))
    except Exception as exc:
        g.db.rollback()
        flash_and_log(f"Error creating name: {exc}", "error")
        return redirect(url_for("names.list_names_view"))

    flash(f"Created name {name.name_text!r}.", "success")
    return redirect(url_for("names.detail", name_id=name.id))


@bp.route("/<int:name_id>")
def detail(name_id: int) -> Union[str, Response]:
    """Show one name, its renderings, and where it is used."""
    name = get_name_by_id(g.db, name_id)
    if name is None:
        flash("Name not found", "error")
        return redirect(url_for("names.list_names_view"))

    usage_count = g.db.query(SentenceWord).filter(SentenceWord.name_id == name_id).count()

    return render_template(
        "names/detail.html",
        name=name,
        renderings=get_name_renderings(g.db, name),
        usage_count=usage_count,
        language_names=get_supported_languages(),
        name_kinds=NAME_KINDS,
        name_kind_labels=NAME_KIND_LABELS,
        name_genders=NAME_GENDERS,
        rendering_kinds=RENDERING_KINDS,
        rendering_kind_labels=RENDERING_KIND_LABELS,
    )


@bp.route("/<int:name_id>/update", methods=["POST"])
def update(name_id: int) -> Response:
    """Update a name's kind, disambiguation, gender, or verified flag."""
    if _is_readonly():
        flash("Cannot edit names in read-only mode", "error")
        return redirect(url_for("names.detail", name_id=name_id))

    name = get_name_by_id(g.db, name_id)
    if name is None:
        flash("Name not found", "error")
        return redirect(url_for("names.list_names_view"))

    try:
        update_name(
            g.db,
            name,
            kind=request.form.get("kind", name.kind),
            disambiguation=request.form.get("disambiguation", "").strip() or None,
            gender=request.form.get("gender", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
            verified=request.form.get("verified") == "on",
            source=Config.OPERATION_LOG_SOURCE,
        )
        g.db.commit()
        flash("Name updated.", "success")
    except ValueError as exc:
        g.db.rollback()
        flash(str(exc), "error")
    except Exception as exc:
        g.db.rollback()
        flash_and_log(f"Error updating name: {exc}", "error")

    return redirect(url_for("names.detail", name_id=name_id))


@bp.route("/<int:name_id>/renderings", methods=["POST"])
def set_rendering(name_id: int) -> Response:
    """Set how a name is written in one language."""
    if _is_readonly():
        flash("Cannot edit names in read-only mode", "error")
        return redirect(url_for("names.detail", name_id=name_id))

    name = get_name_by_id(g.db, name_id)
    if name is None:
        flash("Name not found", "error")
        return redirect(url_for("names.list_names_view"))

    language_code = request.form.get("language_code", "").strip()
    rendering = request.form.get("translation", "").strip()
    rendering_kind = request.form.get("rendering_kind", "").strip() or DEFAULT_RENDERING_KIND
    if not language_code:
        flash("Pick a language for the rendering", "error")
        return redirect(url_for("names.detail", name_id=name_id))

    try:
        set_name_translation(
            g.db,
            name,
            language_code=language_code,
            translation=rendering,
            rendering_kind=rendering_kind,
            phonetic_pronunciation=request.form.get("phonetic", "").strip() or None,
            verified=True,
            source=Config.OPERATION_LOG_SOURCE,
        )
        g.db.commit()
        flash(
            f"Set the {language_code} {rendering_kind} of {name.name_text!r}.",
            "success",
        )
    except ValueError as exc:
        g.db.rollback()
        flash(str(exc), "error")
    except Exception as exc:
        g.db.rollback()
        flash_and_log(f"Error saving rendering: {exc}", "error")

    return redirect(url_for("names.detail", name_id=name_id))


@bp.route("/<int:name_id>/renderings/<int:rendering_id>/delete", methods=["POST"])
def delete_rendering(name_id: int, rendering_id: int) -> Response:
    """Remove one language's rendering of a name."""
    if _is_readonly():
        flash("Cannot edit names in read-only mode", "error")
        return redirect(url_for("names.detail", name_id=name_id))

    rendering = (
        g.db.query(NameTranslation)
        .filter(NameTranslation.id == rendering_id, NameTranslation.name_id == name_id)
        .first()
    )
    if rendering is None:
        flash("Rendering not found", "error")
        return redirect(url_for("names.detail", name_id=name_id))

    language_code = rendering.language_code
    g.db.delete(rendering)
    g.db.commit()
    flash(f"Removed the {language_code} rendering.", "success")
    return redirect(url_for("names.detail", name_id=name_id))


@bp.route("/<int:name_id>/delete", methods=["POST"])
def delete(name_id: int) -> Response:
    """Delete a name.

    Sentence words that pointed at it keep their text and fall back to being
    unresolved, which is exactly how they would look had the name never been
    registered.
    """
    if _is_readonly():
        flash("Cannot delete names in read-only mode", "error")
        return redirect(url_for("names.detail", name_id=name_id))

    name = get_name_by_id(g.db, name_id)
    if name is None:
        flash("Name not found", "error")
        return redirect(url_for("names.list_names_view"))

    name_text = name.name_text
    g.db.query(SentenceWord).filter(SentenceWord.name_id == name_id).update(
        {SentenceWord.name_id: None}, synchronize_session=False
    )
    delete_name(g.db, name, source=Config.OPERATION_LOG_SOURCE)
    g.db.commit()
    flash(f"Deleted name {name_text!r}.", "success")
    return redirect(url_for("names.list_names_view"))
