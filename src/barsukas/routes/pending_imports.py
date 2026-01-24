#!/usr/bin/python3

"""Routes for viewing pending imports."""

from barsukas.config import Config
from flask import Blueprint, g, render_template, request
from flask.typing import ResponseReturnValue

from wordfreq.storage.models.imports import PendingImport

bp = Blueprint("pending_imports", __name__, url_prefix="/pending-imports")


@bp.route("/")
def list_pending_imports() -> ResponseReturnValue:
    """List pending imports with pagination and filtering."""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    pos_type_filter = request.args.get("pos_type", "").strip()
    pos_subtype_filter = request.args.get("pos_subtype", "").strip()
    source_filter = request.args.get("source", "").strip()
    language_filter = request.args.get("language", "").strip()

    # Build query
    query = g.db.query(PendingImport)

    # Apply filters
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

    # Order by most recent first
    query = query.order_by(PendingImport.added_at.desc())

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
