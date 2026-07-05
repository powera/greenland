"""Read-only query helpers for the TextWork model (the story library)."""

from typing import List, Optional

from sqlalchemy.orm import Query, Session

from storage.models.concept import normalize_concept_slug
from storage.models.text_work import TextWork


def _filtered_text_works_query(
    session: Session,
    search: str,
    text_type: Optional[str],
) -> "Query[TextWork]":
    """Return a TextWork query with the search/type filters applied."""
    query = session.query(TextWork)

    if search.strip():
        # Match the slug using the same space/underscore equivalence used at
        # insert time, and also match the free-text summary and attribution.
        slug_term = f"%{normalize_concept_slug(search)}%"
        text_term = f"%{search.strip()}%"
        query = query.filter(
            TextWork.slug.ilike(slug_term)
            | TextWork.summary.ilike(text_term)
            | TextWork.attribution.ilike(text_term)
        )

    if text_type:
        query = query.filter(TextWork.text_type == text_type)

    return query


def list_text_works(
    session: Session,
    search: str = "",
    text_type: Optional[str] = None,
    limit: int = 0,
    offset: int = 0,
) -> List[TextWork]:
    """List text works, optionally filtered by a search term and type.

    Args:
        session: Database session (concepts backend).
        search: Case-insensitive substring matched against slug, summary, and
            attribution, with the concepts' space/underscore equivalence.
        text_type: If set, return only works of this type.
        limit: Maximum rows to return; 0 means no limit.
        offset: Number of rows to skip (for pagination); ignored when 0.

    Returns:
        Text works ordered alphabetically by slug.
    """
    query = _filtered_text_works_query(session, search, text_type)
    query = query.order_by(TextWork.slug.asc())

    if offset > 0:
        query = query.offset(offset)
    if limit > 0:
        query = query.limit(limit)

    return query.all()


def count_text_works(
    session: Session,
    search: str = "",
    text_type: Optional[str] = None,
) -> int:
    """Return the number of text works matching the search/type filters."""
    return _filtered_text_works_query(session, search, text_type).count()


def list_text_works_attributed_to(session: Session, qid: str) -> List[TextWork]:
    """Return the works attributed to a person/source Q-id, ordered by slug.

    This powers the "Attributed texts" list on a person's concept page: many
    works (poems, speeches, later quotes) may hang off one attribution Q-id.
    """
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return []
    return (
        session.query(TextWork)
        .filter(TextWork.attribution_qid == normalized_qid)
        .order_by(TextWork.slug.asc())
        .all()
    )
