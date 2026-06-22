"""Read-only query helpers for the Concept model.

Includes light wiki-style helpers (backlinks, wanted pages) that work purely by
scanning concept bodies for ``[[...]]`` references, so they need no link table.
"""

from typing import List, Set

from sqlalchemy.orm import Query, Session

from storage.models.concept import (
    Concept,
    normalize_concept_slug,
    parse_wiki_links,
)


def _filtered_concepts_query(
    session: Session,
    search: str,
    verified_only: bool,
) -> "Query[Concept]":
    """Return a Concept query with the search/verified filters applied."""
    query = session.query(Concept)

    if search.strip():
        # Match the slug using the same space/underscore equivalence used at
        # insert time, and also match the free-text summary.
        slug_term = f"%{normalize_concept_slug(search)}%"
        summary_term = f"%{search.strip()}%"
        query = query.filter(Concept.slug.ilike(slug_term) | Concept.summary.ilike(summary_term))

    if verified_only:
        query = query.filter(Concept.verified.is_(True))

    return query


def list_concepts(
    session: Session,
    search: str = "",
    verified_only: bool = False,
    limit: int = 0,
    offset: int = 0,
) -> List[Concept]:
    """List concepts, optionally filtered by a search term and verification.

    Args:
        session: Database session.
        search: Case-insensitive substring matched against slug and summary.
            Spaces are treated like underscores so "civil war" matches
            "Civil_War".
        verified_only: If True, return only verified concepts.
        limit: Maximum rows to return; 0 means no limit.
        offset: Number of rows to skip (for pagination); ignored when 0.

    Returns:
        Concepts ordered alphabetically by slug.
    """
    query = _filtered_concepts_query(session, search, verified_only)
    query = query.order_by(Concept.slug.asc())

    if offset > 0:
        query = query.offset(offset)
    if limit > 0:
        query = query.limit(limit)

    return query.all()


def count_concepts(
    session: Session,
    search: str = "",
    verified_only: bool = False,
) -> int:
    """Return the number of concepts matching the search/verified filters."""
    return _filtered_concepts_query(session, search, verified_only).count()


def get_backlinks(session: Session, slug: str) -> List[Concept]:
    """Return concepts whose body links to the given slug via ``[[...]]``.

    Args:
        session: Database session.
        slug: The target slug (any space/underscore form).

    Returns:
        Concepts that reference the target, ordered by slug.
    """
    target = normalize_concept_slug(slug)
    backlinks: List[Concept] = []
    for concept in (
        session.query(Concept).filter(Concept.body.isnot(None)).order_by(Concept.slug.asc())
    ):
        body = concept.body or ""
        if any(link.target_slug == target for link in parse_wiki_links(body)):
            backlinks.append(concept)
    return backlinks


def get_wanted_slugs(session: Session) -> List[str]:
    """Return wiki-link targets that no concept exists for yet ("wanted pages").

    Scans every concept body for ``[[...]]`` references and returns the set of
    targets that have no matching :class:`Concept`, sorted alphabetically.

    Args:
        session: Database session.

    Returns:
        Sorted list of canonical slugs that are linked-to but missing.
    """
    existing: Set[str] = {
        row.slug for row in session.query(Concept.slug).all()  # type: ignore[attr-defined]
    }
    wanted: Set[str] = set()
    for concept in session.query(Concept).filter(Concept.body.isnot(None)):
        for link in parse_wiki_links(concept.body or ""):
            if link.target_slug and link.target_slug not in existing:
                wanted.add(link.target_slug)
    return sorted(wanted)
