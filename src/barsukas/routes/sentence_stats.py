#!/usr/bin/python3

"""Routes for sentence word statistics."""

from flask import Blueprint, g, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import func

from barsukas.config import Config
from wordfreq.storage.models.schema import Lemma, SentenceWord

bp = Blueprint("sentence_stats", __name__, url_prefix="/sentence-stats")


@bp.route("/")
def index() -> ResponseReturnValue:
    """Show word usage statistics from the sentences corpus."""
    page = request.args.get("page", 1, type=int)
    min_level = request.args.get("min_level", "", type=str).strip()
    max_level = request.args.get("max_level", "", type=str).strip()
    pos_type = request.args.get("pos_type", "").strip()
    pos_subtype = request.args.get("pos_subtype", "").strip()
    sort_by = request.args.get("sort_by", "count_desc").strip()
    min_count = request.args.get("min_count", "", type=str).strip()

    # Base query: count word occurrences in sentences, grouped by lemma
    query = (
        g.db.query(
            Lemma.id,
            Lemma.lemma_text,
            Lemma.definition_text,
            Lemma.pos_type,
            Lemma.pos_subtype,
            Lemma.difficulty_level,
            func.count(SentenceWord.id).label("sentence_count"),
        )
        .join(SentenceWord, SentenceWord.lemma_id == Lemma.id)
        .group_by(
            Lemma.id,
            Lemma.lemma_text,
            Lemma.definition_text,
            Lemma.pos_type,
            Lemma.pos_subtype,
            Lemma.difficulty_level,
        )
    )

    # Apply level filters
    if min_level:
        try:
            min_level_int = int(min_level)
            query = query.filter(Lemma.difficulty_level >= min_level_int)
        except ValueError:
            pass

    if max_level:
        try:
            max_level_int = int(max_level)
            query = query.filter(Lemma.difficulty_level <= max_level_int)
        except ValueError:
            pass

    # Apply POS type filter
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    # Apply POS subtype filter
    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)

    # Apply minimum count filter
    if min_count:
        try:
            min_count_int = int(min_count)
            query = query.having(func.count(SentenceWord.id) >= min_count_int)
        except ValueError:
            pass

    # Apply sorting
    if sort_by == "count_desc":
        query = query.order_by(func.count(SentenceWord.id).desc())
    elif sort_by == "count_asc":
        query = query.order_by(func.count(SentenceWord.id).asc())
    elif sort_by == "level_desc":
        query = query.order_by(Lemma.difficulty_level.desc().nullslast())
    elif sort_by == "level_asc":
        query = query.order_by(Lemma.difficulty_level.asc().nullsfirst())
    elif sort_by == "word_asc":
        query = query.order_by(Lemma.lemma_text.asc())
    elif sort_by == "word_desc":
        query = query.order_by(Lemma.lemma_text.desc())
    else:
        query = query.order_by(func.count(SentenceWord.id).desc())

    # Get total count for pagination (using a subquery)
    count_query = query.subquery()
    total = g.db.query(func.count()).select_from(count_query).scalar() or 0

    # Paginate
    stats = query.limit(Config.ITEMS_PER_PAGE).offset((page - 1) * Config.ITEMS_PER_PAGE).all()

    # Calculate pagination
    total_pages = (total + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE

    # Get filter options
    pos_types = [
        row[0]
        for row in g.db.query(Lemma.pos_type)
        .filter(Lemma.pos_type.isnot(None))
        .distinct()
        .order_by(Lemma.pos_type)
        .all()
    ]

    # Get subtypes, optionally filtered by selected pos_type
    subtype_query = g.db.query(Lemma.pos_subtype).filter(Lemma.pos_subtype.isnot(None))
    if pos_type:
        subtype_query = subtype_query.filter(Lemma.pos_type == pos_type)
    pos_subtypes = [row[0] for row in subtype_query.distinct().order_by(Lemma.pos_subtype).all()]

    # Calculate summary statistics
    summary_query = g.db.query(
        func.count(func.distinct(SentenceWord.lemma_id)).label("unique_words"),
        func.count(SentenceWord.id).label("total_occurrences"),
    ).filter(SentenceWord.lemma_id.isnot(None))
    summary = summary_query.first()
    unique_words = summary[0] if summary else 0
    total_occurrences = summary[1] if summary else 0

    return render_template(
        "sentence_stats/index.html",
        stats=stats,
        page=page,
        total_pages=total_pages,
        total=total,
        min_level=min_level,
        max_level=max_level,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        pos_types=pos_types,
        pos_subtypes=pos_subtypes,
        sort_by=sort_by,
        min_count=min_count,
        unique_words=unique_words,
        total_occurrences=total_occurrences,
    )
