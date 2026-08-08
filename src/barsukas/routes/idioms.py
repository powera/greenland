#!/usr/bin/python3

"""Routes for browsing idioms.

Idioms (figurative expressions like "kick the bucket") live in their own
``idioms`` table. This blueprint renders them through the shared ``elements/``
templates, so the list table, identity block, and pagination are the same code
the phrase views use.

What stays idiom-specific is the equivalents section. Unlike a phrase, an idiom
is anchored to a source language and may have zero, one, or several equivalents
per target language, each with its own equivalence kind. That asymmetry is real
rather than incidental, so it gets its own rendering instead of being forced
through the shared single-value language table.

Read-only for now: the add/edit path is deferred until phrases, idioms, and
sentences get a unified creation flow.
"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from barsukas.config import Config
from barsukas.helpers.elements import build_element_rows, group_language_values
from storage.crud.idiom import (
    get_idiom_by_id,
    list_idiom_source_languages,
    list_idioms,
)
from storage.translation_helpers import get_supported_languages

bp = Blueprint("idioms", __name__, url_prefix="/idioms")


@bp.route("/")
def list_idioms_view() -> ResponseReturnValue:
    """List idioms, optionally filtered by source language."""
    source_language = request.args.get("source_language", "").strip()
    page = request.args.get("page", 1, type=int)

    _, total = list_idioms(g.db, source_language_code=source_language or None)
    total_pages = max(1, (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))

    idioms, _ = list_idioms(
        g.db,
        source_language_code=source_language or None,
        limit=Config.ITEMS_PER_PAGE,
        offset=(page - 1) * Config.ITEMS_PER_PAGE,
    )

    rows = build_element_rows(
        idioms,
        {idiom.id: url_for("idioms.view_idiom", idiom_id=idiom.id) for idiom in idioms},
    )

    return render_template(
        "idioms/list.html",
        rows=rows,
        source_language_by_id={idiom.id: idiom.source_language_code for idiom in idioms},
        equivalent_counts={idiom.id: len(idiom.equivalents) for idiom in idioms},
        source_language=source_language,
        source_languages=list_idiom_source_languages(g.db),
        language_names=get_supported_languages(),
        page=page,
        total=total,
        total_pages=total_pages,
    )


@bp.route("/<int:idiom_id>")
def view_idiom(idiom_id: int) -> ResponseReturnValue:
    """View a single idiom with its equivalents grouped by language."""
    idiom = get_idiom_by_id(g.db, idiom_id)
    if not idiom:
        flash("Idiom not found", "error")
        return redirect(url_for("idioms.list_idioms_view"))

    language_names = get_supported_languages()

    # The source language is not a language an idiom can lack an equivalent in:
    # its expression is the thing the equivalents are equivalent to. Dropping it
    # here rather than in the template keeps the shared table's "show a row per
    # supported language" rule intact.
    equivalent_language_names = {
        code: name for code, name in language_names.items() if code != idiom.source_language_code
    }

    return render_template(
        "idioms/view.html",
        idiom=idiom,
        values_by_language=group_language_values(idiom.language_values),
        equivalent_language_names=equivalent_language_names,
        language_names=language_names,
    )
