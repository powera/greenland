#!/usr/bin/python3

"""Routes for viewing pending imports."""

import logging
from typing import Any, cast

from barsukas.config import Config
from agents.dramblys.staging import approve_pending_import, reject_pending_import
from workqueue.task_queue import TaskType, enqueue_task
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import Query

from storage.models.imports import PendingImport

bp = Blueprint("pending_imports", __name__, url_prefix="/pending-imports")
logger = logging.getLogger(__name__)


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
            new_lemma_id = result.get("lemma_id")
            if new_lemma_id:
                try:
                    enqueue_task(
                        g.db,
                        task_type=TaskType.ADD_MISSING_TRANSLATIONS,
                        target_type="lemma",
                        target_id=new_lemma_id,
                        payload={"lemma_id": new_lemma_id},
                        dedup_key=f"{TaskType.ADD_MISSING_TRANSLATIONS}:{new_lemma_id}",
                    )
                    flash("Queued translation generation for all tier 1/2 languages.", "info")
                except Exception as enqueue_exc:
                    logger.warning(
                        "Could not enqueue translations for lemma %s: %s", new_lemma_id, enqueue_exc
                    )
        else:
            flash(result.get("error", "Failed to approve pending import"), "error")
    except Exception as exc:
        g.db.rollback()
        flash(f"Error approving pending import: {exc}", "error")

    return redirect(url_for("pending_imports.list_pending_imports"))


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

    return redirect(url_for("pending_imports.list_pending_imports"))


@bp.route("/<int:pending_import_id>/detail")
def detail(pending_import_id: int) -> ResponseReturnValue:
    """Show detail/status page for a single pending import."""
    pending = g.db.query(PendingImport).filter(PendingImport.id == pending_import_id).first()
    if not pending:
        abort(404)
    return render_template("pending_imports/detail.html", item=pending)


@bp.route("/<int:pending_import_id>/stage", methods=["POST"])
def stage(pending_import_id: int) -> ResponseReturnValue:
    """AJAX endpoint: query LLM and store pos_subtype/definition back into PendingImport."""
    if current_app.config.get("READONLY", False):
        return jsonify({"success": False, "error": "Cannot modify data in read-only mode"}), 403

    pending = g.db.query(PendingImport).filter(PendingImport.id == pending_import_id).first()
    if not pending:
        return jsonify({"success": False, "error": "Pending import not found"}), 404

    model_name = str(current_app.config.get("DEFAULT_LLM_MODEL", "gpt-5.4-mini"))
    db_path = str(current_app.config.get("DB_PATH", Config.DB_PATH))
    debug = bool(current_app.config.get("DEBUG", False))

    try:
        from wordfreq.translation.client import LinguisticClient

        client = LinguisticClient(model=model_name, db_path=db_path, debug=debug)
        definitions_list, llm_success = client.query_definitions(pending.english_word)

        if not llm_success or not definitions_list:
            return jsonify(
                {
                    "success": False,
                    "error": f"LLM returned no definitions for '{pending.english_word}'",
                }
            )

        # Filter to matching pos_type if the pending import has one
        if pending.pos_type:
            matching = [d for d in definitions_list if d.get("pos") == pending.pos_type]
            if matching:
                definitions_list = matching

        # Use the first matching definition to populate the stored fields
        first = definitions_list[0]
        pending.pos_type = first.get("pos") or pending.pos_type
        pending.pos_subtype = first.get("pos_subtype") or pending.pos_subtype
        if first.get("definition"):
            pending.definition = first["definition"]
        g.db.commit()

        return jsonify({"success": True, "definitions": definitions_list})

    except Exception as exc:
        g.db.rollback()
        logger.exception("Error staging pending import %d", pending_import_id)
        return jsonify({"success": False, "error": str(exc)}), 500


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
