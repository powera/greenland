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

The same asymmetry is why the add/edit path here is a plain per-type form rather
than a shared one. The ``elements/`` templates generalize the *read* side, where
every type displays the same few facts. Writing is where the types stop being
alike: an idiom needs a required equivalence kind per value, allows several
values per language, and validates through ``crud.idiom``, none of which a
phrase does. A descriptor-driven shared form would have to encode all of that,
which is a form framework rather than a configuration - so the view pages keep
using the shared templates and the edit pages stay siblings.
"""

from typing import Any, List, Optional

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
from barsukas.helpers.flash_helpers import log_and_flash_error
from storage.crud.idiom import (
    add_idiom_equivalent,
    create_idiom,
    delete_idiom,
    delete_idiom_equivalent,
    get_idiom_by_id,
    list_idiom_source_languages,
    list_idioms,
)
from storage.crud.operation_log import (
    IDIOM_EQUIVALENT_UPDATE,
    IDIOM_UPDATE,
    FieldChange,
    log_field_changes,
)
from storage.models.idiom import IDIOM_EQUIVALENCE_KINDS
from storage.translation_helpers import get_supported_languages
from workqueue.task_queue import enqueue_task

bp = Blueprint("idioms", __name__, url_prefix="/idioms")

# Blank equivalent rows offered at the bottom of the edit form. Enough to add a
# few at once without the page becoming mostly empty inputs; adding more is a
# save and a revisit.
_NEW_EQUIVALENT_ROWS = 3

# Canonical capability task names, matching workqueue.registry. These are the
# same names agents.gegute enqueues, so work queued from this page and from the
# CLI dedups against each other.
TASK_POPULATE_EQUIVALENTS = "idioms.equivalents.populate"
TASK_VALIDATE_EQUIVALENTS = "idioms.equivalents.validate"


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


@bp.route("/new", methods=["GET", "POST"])
def new_idiom() -> ResponseReturnValue:
    """Create an idiom from its source expression and meaning.

    Equivalents are not collected here. An idiom is identified by its
    expression and meaning; the equivalents are a separate, longer job best
    done on the edit page against a saved row - or by gegute.
    """
    if request.method == "POST":
        if current_app.config.get("READONLY", False):
            flash("Cannot create: running in read-only mode", "error")
            return redirect(url_for("idioms.list_idioms_view"))

        expression = request.form.get("expression", "").strip()
        meaning = request.form.get("meaning", "").strip()
        source_language_code = request.form.get("source_language_code", "").strip()

        # crud.idiom validates these too, but it raises; catching the empty
        # case here keeps a mistyped form on the form with its values intact.
        if not expression or not meaning or not source_language_code:
            flash("Source language, expression, and meaning are all required", "error")
            return render_template(
                "idioms/edit.html",
                idiom=None,
                form=request.form,
                language_names=get_supported_languages(),
                equivalence_kinds=IDIOM_EQUIVALENCE_KINDS,
                new_equivalent_rows=_NEW_EQUIVALENT_ROWS,
            )

        idiom = create_idiom(
            g.db,
            source_language_code=source_language_code,
            expression=expression,
            meaning=meaning,
            usage_note=request.form.get("usage_note", "").strip() or None,
            register=request.form.get("register", "").strip() or None,
            region=request.form.get("region", "").strip() or None,
            difficulty_level=_parse_int(request.form.get("difficulty_level", "").strip()),
            notes=request.form.get("notes", "").strip() or None,
            verified=request.form.get("verified") == "on",
            source=Config.OPERATION_LOG_SOURCE,
        )
        g.db.commit()

        flash(f"Created idiom: {idiom.expression}", "success")
        return redirect(url_for("idioms.view_idiom", idiom_id=idiom.id))

    return render_template(
        "idioms/edit.html",
        idiom=None,
        form={},
        language_names=get_supported_languages(),
        equivalence_kinds=IDIOM_EQUIVALENCE_KINDS,
        new_equivalent_rows=_NEW_EQUIVALENT_ROWS,
    )


@bp.route("/<int:idiom_id>/edit", methods=["GET", "POST"])
def edit_idiom(idiom_id: int) -> ResponseReturnValue:
    """Edit an idiom's metadata and its equivalents."""
    idiom = get_idiom_by_id(g.db, idiom_id)
    if not idiom:
        flash("Idiom not found", "error")
        return redirect(url_for("idioms.list_idioms_view"))

    if request.method == "POST":
        if current_app.config.get("READONLY", False):
            flash("Cannot update: running in read-only mode", "error")
            return redirect(url_for("idioms.view_idiom", idiom_id=idiom_id))

        idiom_changes: List[FieldChange] = []

        for field_name in ("expression", "meaning"):
            new_value = request.form.get(field_name, "").strip()
            old_value = getattr(idiom, field_name)
            # Required fields: a blank submission is a mistake rather than a
            # request to clear, so it is ignored instead of writing an empty
            # string past the crud layer's validation.
            if new_value and new_value != old_value:
                idiom_changes.append(FieldChange(field_name, old_value, new_value))
                setattr(idiom, field_name, new_value)

        for field_name in ("usage_note", "register", "region", "notes"):
            new_optional = request.form.get(field_name, "").strip() or None
            old_optional = getattr(idiom, field_name)
            if new_optional != old_optional:
                idiom_changes.append(FieldChange(field_name, old_optional, new_optional))
                setattr(idiom, field_name, new_optional)

        new_difficulty = _parse_int(request.form.get("difficulty_level", "").strip())
        if new_difficulty != idiom.difficulty_level:
            idiom_changes.append(
                FieldChange("difficulty_level", idiom.difficulty_level, new_difficulty)
            )
            idiom.difficulty_level = new_difficulty

        new_verified = request.form.get("verified") == "on"
        if new_verified != idiom.verified:
            idiom_changes.append(FieldChange("verified", idiom.verified, new_verified))
            idiom.verified = new_verified

        _log_idiom_changes(idiom, idiom_changes)

        _apply_equivalent_edits(idiom)
        _apply_new_equivalents(idiom)

        g.db.commit()
        flash("Idiom updated", "success")
        return redirect(url_for("idioms.view_idiom", idiom_id=idiom_id))

    return render_template(
        "idioms/edit.html",
        idiom=idiom,
        form={},
        language_names=get_supported_languages(),
        equivalence_kinds=IDIOM_EQUIVALENCE_KINDS,
        new_equivalent_rows=_NEW_EQUIVALENT_ROWS,
    )


@bp.route("/<int:idiom_id>/delete", methods=["POST"])
def delete_idiom_view(idiom_id: int) -> ResponseReturnValue:
    """Delete an idiom and its equivalents via cascade."""
    if current_app.config.get("READONLY", False):
        flash("Cannot delete: running in read-only mode", "error")
        return redirect(url_for("idioms.view_idiom", idiom_id=idiom_id))

    idiom = get_idiom_by_id(g.db, idiom_id)
    if not idiom:
        flash("Idiom not found", "error")
        return redirect(url_for("idioms.list_idioms_view"))

    expression = idiom.expression
    delete_idiom(g.db, idiom, source=Config.OPERATION_LOG_SOURCE)
    g.db.commit()

    flash(f"Deleted idiom: {expression}", "success")
    return redirect(url_for("idioms.list_idioms_view"))


@bp.route("/<int:idiom_id>/populate-equivalents", methods=["POST"])
def populate_equivalents(idiom_id: int) -> ResponseReturnValue:
    """Queue equivalent generation for one idiom (gegute's populate mode)."""
    idiom = get_idiom_by_id(g.db, idiom_id)
    if not idiom:
        flash("Idiom not found", "error")
        return redirect(url_for("idioms.list_idioms_view"))

    try:
        result = enqueue_task(
            g.db,
            task_type=TASK_POPULATE_EQUIVALENTS,
            target_type="idiom",
            target_id=idiom_id,
            payload={
                "schema_version": 1,
                "source_component": "barsukas.idioms",
                "idiom_id": idiom_id,
                "only_missing": True,
            },
            dedup_key=f"{TASK_POPULATE_EQUIVALENTS}:{idiom_id}",
        )
        if result.created:
            flash("Queued equivalent generation. Results will be applied soon.", "info")
        else:
            flash("Equivalent generation already in progress for this idiom.", "warning")
    except Exception as error:
        log_and_flash_error(error, "queueing equivalent generation")

    return redirect(url_for("idioms.view_idiom", idiom_id=idiom_id))


@bp.route("/<int:idiom_id>/validate-equivalents", methods=["POST"])
def validate_equivalents(idiom_id: int) -> ResponseReturnValue:
    """Queue an audit of one idiom's equivalents (gegute's validate mode).

    The audit writes nothing; its findings land in the task result, which is
    why this is offered even in read-only mode's absence of a save button.
    """
    idiom = get_idiom_by_id(g.db, idiom_id)
    if not idiom:
        flash("Idiom not found", "error")
        return redirect(url_for("idioms.list_idioms_view"))

    if not idiom.equivalents:
        flash("Nothing to audit: this idiom has no equivalents yet.", "warning")
        return redirect(url_for("idioms.view_idiom", idiom_id=idiom_id))

    try:
        result = enqueue_task(
            g.db,
            task_type=TASK_VALIDATE_EQUIVALENTS,
            target_type="idiom",
            target_id=idiom_id,
            payload={
                "schema_version": 1,
                "source_component": "barsukas.idioms",
                "idiom_id": idiom_id,
            },
            dedup_key=f"{TASK_VALIDATE_EQUIVALENTS}:{idiom_id}",
        )
        if result.created:
            flash(
                "Queued equivalent audit. Findings appear in the task result; "
                "nothing is changed automatically.",
                "info",
            )
        else:
            flash("An audit is already in progress for this idiom.", "warning")
    except Exception as error:
        log_and_flash_error(error, "queueing equivalent audit")

    return redirect(url_for("idioms.view_idiom", idiom_id=idiom_id))


def _apply_equivalent_edits(idiom: Any) -> None:
    """Update or delete existing equivalents from the submitted form.

    Each stored equivalent renders as a row of fields suffixed with its id, so
    a submission names exactly the rows it means. An unchecked delete box and
    an unchanged value both leave the row alone.
    """
    for equivalent in list(idiom.equivalents):
        prefix = f"equivalent_{equivalent.id}"

        if request.form.get(f"{prefix}_delete") == "on":
            delete_idiom_equivalent(g.db, equivalent, source=Config.OPERATION_LOG_SOURCE)
            continue

        # One entry per equivalent per submission, keyed to the parent idiom's
        # GUID. The gloss/note/register edits below went unlogged entirely
        # before; they cost nothing to include now that the changes are batched.
        equivalent_changes: List[FieldChange] = []

        expression = request.form.get(f"{prefix}_expression")
        # A missing key means the row was not rendered; only a present-and-empty
        # value is a real edit, and an empty expression is not storable.
        if expression is not None:
            expression = expression.strip()
            if expression and expression != equivalent.expression:
                equivalent_changes.append(
                    FieldChange("expression", equivalent.expression, expression)
                )
                equivalent.expression = expression

        kind = (request.form.get(f"{prefix}_kind") or "").strip()
        if kind in IDIOM_EQUIVALENCE_KINDS and kind != equivalent.equivalence_kind:
            equivalent_changes.append(
                FieldChange("equivalence_kind", equivalent.equivalence_kind, kind)
            )
            equivalent.equivalence_kind = kind

        for field_name, column_name in (
            ("gloss", "literal_gloss"),
            ("note", "usage_note"),
            ("register", "register"),
        ):
            raw = request.form.get(f"{prefix}_{field_name}")
            if raw is None:
                continue
            new_value = raw.strip() or None
            if new_value != getattr(equivalent, column_name):
                equivalent_changes.append(
                    FieldChange(column_name, getattr(equivalent, column_name), new_value)
                )
                setattr(equivalent, column_name, new_value)

        new_verified = request.form.get(f"{prefix}_verified") == "on"
        if new_verified != equivalent.verified:
            equivalent_changes.append(FieldChange("verified", equivalent.verified, new_verified))
            equivalent.verified = new_verified

        log_field_changes(
            g.db,
            source=Config.OPERATION_LOG_SOURCE,
            operation_type=IDIOM_EQUIVALENT_UPDATE,
            entity_guid=idiom.guid,
            changes=equivalent_changes,
            extra={"language_code": equivalent.language_code},
        )


def _apply_new_equivalents(idiom: Any) -> None:
    """Add equivalents from the blank rows at the bottom of the form.

    The form always renders a few empty rows; those left blank are skipped, so
    the operator adds one or several without a page round-trip per row.
    """
    existing = {
        (row.language_code, (row.expression or "").strip().casefold()) for row in idiom.equivalents
    }

    for index in range(_NEW_EQUIVALENT_ROWS):
        prefix = f"new_equivalent_{index}"
        expression = (request.form.get(f"{prefix}_expression") or "").strip()
        language_code = (request.form.get(f"{prefix}_language") or "").strip()
        kind = (request.form.get(f"{prefix}_kind") or "").strip()

        if not expression or not language_code:
            continue
        if kind not in IDIOM_EQUIVALENCE_KINDS:
            flash(f"Skipped {language_code} equivalent: invalid kind {kind!r}", "error")
            continue

        # The table is unique on (idiom, language, expression); skipping here
        # turns a would-be IntegrityError into an ordinary no-op.
        key = (language_code, expression.casefold())
        if key in existing:
            flash(f"Skipped duplicate {language_code} equivalent: {expression}", "error")
            continue
        existing.add(key)

        add_idiom_equivalent(
            g.db,
            idiom,
            language_code=language_code,
            expression=expression,
            equivalence_kind=kind,
            literal_gloss=(request.form.get(f"{prefix}_gloss") or "").strip() or None,
            usage_note=(request.form.get(f"{prefix}_note") or "").strip() or None,
            register=(request.form.get(f"{prefix}_register") or "").strip() or None,
            verified=request.form.get(f"{prefix}_verified") == "on",
            source=Config.OPERATION_LOG_SOURCE,
        )


def _parse_int(value: str) -> Optional[int]:
    """Parse an integer form value, or None if blank/invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _log_idiom_changes(idiom: Any, changes: List[FieldChange]) -> None:
    """Record a form's worth of idiom field edits as one operation log entry.

    One entry per submission rather than per field, keyed to the idiom's GUID.
    These edits used to go through ``log_translation_change`` one field at a
    time, which recorded no entity reference at all -- the resulting rows named
    a field and two values with nothing to say which idiom they belonged to.
    """
    log_field_changes(
        g.db,
        source=Config.OPERATION_LOG_SOURCE,
        operation_type=IDIOM_UPDATE,
        entity_guid=idiom.guid,
        changes=changes,
    )
