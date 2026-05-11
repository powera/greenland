#!/usr/bin/python3

"""Routes for viewing pending imports.

MIRRORED: routes annotated with ``@mirrored_facade`` have a typed Python
wrapper in the root-level ``api/`` package (``api/batch_operations.py``).
Edits to a mirrored route's path, query params, or response shape MUST be
made in the matching facade in the same commit. See ``api/AGENTS.md``.
"""

import logging
from typing import Any, cast

from barsukas.config import Config
from barsukas.routes._mirror import mirrored_facade
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

from storage.backend.config import DataSourceConfig
from storage.models.imports import PendingImport

bp = Blueprint("pending_imports", __name__, url_prefix="/pending-imports")
logger = logging.getLogger(__name__)


def _get_data_source_config(model_name: str, debug: bool) -> DataSourceConfig:
    """Build DataSourceConfig from the app-level backend config with route overrides."""
    base_config = cast(DataSourceConfig, current_app.backend_config)  # type: ignore[attr-defined]
    return DataSourceConfig(
        backend_type=base_config.backend_type,
        sqlite_path=base_config.sqlite_path,
        jsonl_data_dir=base_config.jsonl_data_dir,
        postgres_url=base_config.postgres_url,
        barsukas_url=base_config.barsukas_url,
        cache_only=base_config.cache_only,
        use_word2vec=base_config.use_word2vec,
        model=model_name,
        debug=debug,
    )


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
        model_name = str(current_app.config.get("DEFAULT_LLM_MODEL", "gpt-5.4-mini"))
        debug = bool(current_app.config.get("DEBUG", False))
        data_source_config = _get_data_source_config(model_name=model_name, debug=debug)
        result = approve_pending_import(
            session=g.db,
            pending_import_id=pending_import_id,
            data_source_config=data_source_config,
            model=model_name,
            debug=debug,
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
    debug = bool(current_app.config.get("DEBUG", False))
    data_source_config = _get_data_source_config(model_name=model_name, debug=debug)

    try:
        from wordfreq.translation.client import LinguisticClient

        # Accept an updated example_sentence from the request and save it before querying
        body = request.get_json(silent=True) or {}
        example_sentence = body.get("example_sentence") or None
        if example_sentence and example_sentence != pending.example_sentence:
            pending.example_sentence = example_sentence
            g.db.flush()

        client = LinguisticClient(config=data_source_config)
        definitions_list, llm_success = client.query_definitions(
            pending.english_word, example_sentence=pending.example_sentence
        )

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


@bp.route("/api/duplicates")
@mirrored_facade("/pending-imports/api/duplicates", "GET")
def api_duplicates() -> ResponseReturnValue:
    """JSON API: find pending imports that are duplicates of existing lemmas.

    A duplicate is either:
    - A direct match: an existing lemma with the same lemma_text and pos_type.
    - A form match: the pending english_word appears as a DerivativeForm
      (language_code='en') of an existing lemma with the same pos_type.

    Only pending imports where definition == english_word (no real definition
    yet) are checked, since staged imports with real definitions need human
    review regardless.

    Returns {"data": [...]} where each item has pending import fields plus
    "match_type" ("direct" or "form"), "matched_lemma_guid", "matched_lemma_text".
    """
    from storage.models.schema import DerivativeForm
    from storage.models import Lemma

    # Only check imports that have not yet been staged (definition = english_word)
    pending_list = (
        g.db.query(PendingImport)
        .filter(PendingImport.definition == PendingImport.english_word)
        .order_by(PendingImport.added_at.desc())
        .all()
    )

    results = []

    for item in pending_list:
        word_lower = item.english_word.lower()
        pos = item.pos_type

        # 1. Direct lemma match
        direct_query = g.db.query(Lemma).filter(Lemma.lemma_text.ilike(word_lower))
        if pos:
            direct_query = direct_query.filter(Lemma.pos_type == pos)
        direct_match = direct_query.first()
        if direct_match:
            results.append(
                {
                    "id": item.id,
                    "english_word": item.english_word,
                    "pos_type": item.pos_type,
                    "source": item.source,
                    "added_at": item.added_at.isoformat() if item.added_at else None,
                    "match_type": "direct",
                    "matched_lemma_guid": direct_match.guid,
                    "matched_lemma_text": direct_match.lemma_text,
                    "matched_pos_type": direct_match.pos_type,
                }
            )
            continue

        # 2. Derivative form match (e.g. "telling" → lemma "tell")
        form_query = (
            g.db.query(DerivativeForm, Lemma)
            .join(Lemma, DerivativeForm.lemma_id == Lemma.id)
            .filter(
                DerivativeForm.derivative_form_text.ilike(word_lower),
                DerivativeForm.language_code == "en",
            )
        )
        if pos:
            form_query = form_query.filter(Lemma.pos_type == pos)
        form_match = form_query.first()
        if form_match:
            _form, matched_lemma = form_match
            results.append(
                {
                    "id": item.id,
                    "english_word": item.english_word,
                    "pos_type": item.pos_type,
                    "source": item.source,
                    "added_at": item.added_at.isoformat() if item.added_at else None,
                    "match_type": "form",
                    "matched_lemma_guid": matched_lemma.guid,
                    "matched_lemma_text": matched_lemma.lemma_text,
                    "matched_pos_type": matched_lemma.pos_type,
                }
            )

    return jsonify(
        {"data": results, "metadata": {"total": len(results), "checked": len(pending_list)}}
    )


@bp.route("/api/list")
@mirrored_facade("/pending-imports/api/list", "GET")
def api_list() -> ResponseReturnValue:
    """JSON API: list pending imports with optional filtering.

    Supports the same query parameters as the HTML list view:
    search, pos_type, pos_subtype, source, language, page.
    Returns {"data": [...], "metadata": {"total": N, "page": P, "total_pages": T}}.
    """
    page = request.args.get("page", 1, type=int)
    query = _build_filtered_query()
    total = query.count()
    imports = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    data = [
        {
            "id": item.id,
            "english_word": item.english_word,
            "definition": item.definition,
            "disambiguation_translation": item.disambiguation_translation,
            "disambiguation_language": item.disambiguation_language,
            "pos_type": item.pos_type,
            "pos_subtype": item.pos_subtype,
            "example_sentence": item.example_sentence,
            "source": item.source,
            "frequency_rank": item.frequency_rank,
            "notes": item.notes,
            "added_at": item.added_at.isoformat() if item.added_at else None,
        }
        for item in imports
    ]
    return jsonify(
        {
            "data": data,
            "metadata": {"total": total, "page": page, "total_pages": total_pages},
        }
    )


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
