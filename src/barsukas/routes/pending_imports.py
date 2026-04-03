#!/usr/bin/python3

"""Routes for viewing pending imports."""

from typing import Any, cast

from barsukas.config import Config
from agents.dramblys.staging import approve_pending_import, reject_pending_import
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import Query

from storage.models.imports import PendingImport

bp = Blueprint("pending_imports", __name__, url_prefix="/pending-imports")


def _build_filtered_query() -> Query[Any]:
    """Build a filtered query for pending imports based on request args."""
    search = request.args.get("search", "").strip()
    pos_type_filter = request.args.get("pos_type", "").strip()
    pos_subtype_filter = request.args.get("pos_subtype", "").strip()
    source_filter = request.args.get("source", "").strip()
    language_filter = request.args.get("language", "").strip()

    query = g.db.query(PendingImport)

    if search:
        query = query.filter(
            (PendingImport.english_word.ilike(f"%{search}%"))
            | (PendingImport.definition.ilike(f"%{search}%"))
            | (PendingImport.disambiguation_translation.ilike(f"%{search}%"))
        )

    if pos_type_filter:
        query = query.filter(PendingImport.pos_type == pos_type_filter)

    if pos_subtype_filter:
        query = query.filter(PendingImport.pos_subtype == pos_subtype_filter)

    if source_filter:
        query = query.filter(PendingImport.source == source_filter)

    if language_filter:
        query = query.filter(PendingImport.disambiguation_language == language_filter)

    return cast(Query[Any], query.order_by(PendingImport.added_at.desc()))


@bp.route("/")
def list_pending_imports() -> ResponseReturnValue:
    """List pending imports with pagination and filtering."""
    page = request.args.get("page", 1, type=int)

    query = _build_filtered_query()

    # Paginate
    total = query.count()
    imports = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    # Get unique values for filter dropdowns
    pos_types = (
        g.db.query(PendingImport.pos_type)
        .distinct()
        .filter(PendingImport.pos_type.isnot(None))
        .order_by(PendingImport.pos_type)
        .all()
    )
    pos_types = [p[0] for p in pos_types if p[0]]

    pos_subtypes = (
        g.db.query(PendingImport.pos_subtype)
        .distinct()
        .filter(PendingImport.pos_subtype.isnot(None))
        .order_by(PendingImport.pos_subtype)
        .all()
    )
    pos_subtypes = [p[0] for p in pos_subtypes if p[0]]

    sources = (
        g.db.query(PendingImport.source)
        .distinct()
        .filter(PendingImport.source.isnot(None))
        .order_by(PendingImport.source)
        .all()
    )
    sources = [s[0] for s in sources if s[0]]

    languages = (
        g.db.query(PendingImport.disambiguation_language)
        .distinct()
        .order_by(PendingImport.disambiguation_language)
        .all()
    )
    languages = [lang[0] for lang in languages if lang[0]]

    # Calculate pagination
    search = request.args.get("search", "").strip()
    pos_type_filter = request.args.get("pos_type", "").strip()
    pos_subtype_filter = request.args.get("pos_subtype", "").strip()
    source_filter = request.args.get("source", "").strip()
    language_filter = request.args.get("language", "").strip()
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    return render_template(
        "pending_imports/list.html",
        imports=imports,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        pos_type_filter=pos_type_filter,
        pos_subtype_filter=pos_subtype_filter,
        source_filter=source_filter,
        language_filter=language_filter,
        pos_types=pos_types,
        pos_subtypes=pos_subtypes,
        sources=sources,
        languages=languages,
    )


@bp.route("/<int:pending_import_id>/approve", methods=["POST"])
def approve(pending_import_id: int) -> ResponseReturnValue:
    """Approve a pending import entry and import it into lemmas."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))

    try:
        db_path_value = str(current_app.config.get("DB_PATH", Config.DB_PATH))
        model_name = str(current_app.config.get("DEFAULT_LLM_MODEL", "gpt-5.4-mini"))
        result = approve_pending_import(
            session=g.db,
            pending_import_id=pending_import_id,
            db_path=db_path_value,
            model=model_name,
            debug=bool(current_app.config.get("DEBUG", False)),
        )
        if result.get("success"):
            flash(result.get("message", f"Approved pending import #{pending_import_id}"), "success")
        else:
            flash(result.get("error", "Failed to approve pending import"), "error")
    except Exception as exc:
        g.db.rollback()
        flash(f"Error approving pending import: {exc}", "error")

    return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))


@bp.route("/<int:pending_import_id>/reject", methods=["POST"])
def reject(pending_import_id: int) -> ResponseReturnValue:
    """Reject a pending import entry and remove it from pending list."""
    if current_app.config.get("READONLY", False):
        flash("Cannot modify data in read-only mode", "error")
        return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))

    try:
        result = reject_pending_import(
            session=g.db,
            pending_import_id=pending_import_id,
            reason="barsukas_manual_rejection",
            add_to_exclusions=True,
        )
        if result.get("success"):
            flash(result.get("message", f"Rejected pending import #{pending_import_id}"), "success")
        else:
            flash(result.get("error", "Failed to reject pending import"), "error")
    except Exception as exc:
        g.db.rollback()
        flash(f"Error rejecting pending import: {exc}", "error")

    return redirect(request.referrer or url_for("pending_imports.list_pending_imports"))


@bp.route("/export.txt")
def export_text() -> Response:
    """Export filtered pending imports as a tab-separated text file."""
    query = _build_filtered_query()
    imports = query.all()

    lines = ["Word\tDefinition\tPOS"]
    for item in imports:
        pos = item.pos_type or ""
        if item.pos_subtype:
            pos += f"/{item.pos_subtype}"
        lines.append(f"{item.english_word}\t{item.definition}\t{pos}")

    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=pending_imports.txt"},
    )
