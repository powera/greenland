"""Read-only query helpers for the Concept and SubConcept models.

Includes light wiki-style helpers (backlinks, wanted pages, link-target
resolution) that work purely by scanning concept bodies for ``[[...]]``
references, so they need no link table.
"""

from typing import Dict, List, NamedTuple, Optional, Set

from sqlalchemy.orm import Query, Session

from storage.models.concept import (
    Concept,
    ConceptWikidataIndex,
    SubConcept,
    concept_slug_to_title,
    normalize_concept_slug,
    parse_wiki_links,
    wiki_target_qid,
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


def _filtered_sub_concepts_query(
    session: Session,
    search: str,
    category: Optional[str],
) -> "Query[SubConcept]":
    """Return a SubConcept query with the search/category filters applied."""
    query = session.query(SubConcept)

    if search.strip():
        slug_term = f"%{normalize_concept_slug(search)}%"
        summary_term = f"%{search.strip()}%"
        query = query.filter(
            SubConcept.slug.ilike(slug_term) | SubConcept.summary.ilike(summary_term)
        )

    if category:
        query = query.filter(SubConcept.category == category)

    return query


def list_sub_concepts(
    session: Session,
    search: str = "",
    category: Optional[str] = None,
    limit: int = 0,
    offset: int = 0,
) -> List[SubConcept]:
    """List sub-concepts, optionally filtered by a search term and category.

    Args:
        session: Database session.
        search: Case-insensitive substring matched against slug and summary,
            with the same space/underscore equivalence as :func:`list_concepts`.
        category: If set, return only sub-concepts in this category.
        limit: Maximum rows to return; 0 means no limit.
        offset: Number of rows to skip (for pagination); ignored when 0.

    Returns:
        Sub-concepts ordered alphabetically by slug.
    """
    query = _filtered_sub_concepts_query(session, search, category)
    query = query.order_by(SubConcept.slug.asc())

    if offset > 0:
        query = query.offset(offset)
    if limit > 0:
        query = query.limit(limit)

    return query.all()


def count_sub_concepts(
    session: Session,
    search: str = "",
    category: Optional[str] = None,
) -> int:
    """Return the number of sub-concepts matching the search/category filters."""
    return _filtered_sub_concepts_query(session, search, category).count()


def get_all_known_slugs(session: Session) -> Set[str]:
    """Return the union of concept and sub-concept slugs.

    This is the "existing page" set for red-link purposes: a slug present in
    either table is never a wanted page.
    """
    slugs: Set[str] = {row[0] for row in session.query(Concept.slug).all()}
    slugs.update(row[0] for row in session.query(SubConcept.slug).all())
    return slugs


class ResolvedWikiTarget(NamedTuple):
    """Where a wiki-link target resolves to.

    Attributes:
        kind: "concept" or "sub_concept".
        slug: The canonical slug of the resolved page (for URL building).
        title: The human-readable title of the resolved page.
    """

    kind: str
    slug: str
    title: str


def resolve_wiki_link_targets(session: Session, body: str) -> Dict[str, ResolvedWikiTarget]:
    """Resolve every ``[[...]]`` target in a body to a concept or sub-concept.

    Resolution is deterministic: a slug target resolves to the main concept
    first, then to a sub-concept with the same slug. A Q-id target (e.g.
    ``[[Q103632]]``) resolves through the shared Wikidata index to whichever
    table the Q-id points at -- this is how links stay specific when a slug is
    ambiguous. Unresolvable targets are simply absent from the result (they
    render as plain text).

    Args:
        session: Database session (concepts backend).
        body: A concept body containing ``[[...]]`` links.

    Returns:
        Mapping of each resolvable target slug (as produced by
        ``parse_wiki_links``, e.g. "Abraham_Lincoln" or "Q42") to its
        :class:`ResolvedWikiTarget`.
    """
    targets = {link.target_slug for link in parse_wiki_links(body or "") if link.target_slug}
    if not targets:
        return {}

    qid_targets = {target: qid for target in targets if (qid := wiki_target_qid(target))}
    slug_targets = {target for target in targets if target not in qid_targets}

    resolved: Dict[str, ResolvedWikiTarget] = {}

    if slug_targets:
        for (slug,) in session.query(SubConcept.slug).filter(SubConcept.slug.in_(slug_targets)):
            resolved[slug] = ResolvedWikiTarget("sub_concept", slug, concept_slug_to_title(slug))
        # Main concepts win over same-slug sub-concepts (deterministic order).
        for (slug,) in session.query(Concept.slug).filter(Concept.slug.in_(slug_targets)):
            resolved[slug] = ResolvedWikiTarget("concept", slug, concept_slug_to_title(slug))

    if qid_targets:
        rows = (
            session.query(ConceptWikidataIndex)
            .filter(ConceptWikidataIndex.qid.in_(set(qid_targets.values())))
            .all()
        )
        by_qid = {row.qid: row for row in rows}
        for target, qid in qid_targets.items():
            row = by_qid.get(qid)
            if row is None:
                continue
            if row.concept is not None:
                resolved[target] = ResolvedWikiTarget(
                    "concept", row.concept.slug, row.concept.title
                )
            elif row.sub_concept is not None:
                resolved[target] = ResolvedWikiTarget(
                    "sub_concept", row.sub_concept.slug, row.sub_concept.title
                )

    return resolved


def get_backlinks(session: Session, slug: str, qids: Optional[List[str]] = None) -> List[Concept]:
    """Return concepts whose body links to the given slug via ``[[...]]``.

    Args:
        session: Database session.
        slug: The target slug (any space/underscore form).
        qids: Optional Q-ids of the target page; bodies linking via a
            ``[[Q...]]`` target for one of these also count as backlinks.

    Returns:
        Concepts that reference the target, ordered by slug.
    """
    target = normalize_concept_slug(slug)
    target_qids = set(qids or [])
    backlinks: List[Concept] = []
    for concept in (
        session.query(Concept).filter(Concept.body.isnot(None)).order_by(Concept.slug.asc())
    ):
        body = concept.body or ""
        for link in parse_wiki_links(body):
            if link.target_slug == target or (
                target_qids and wiki_target_qid(link.target_slug) in target_qids
            ):
                backlinks.append(concept)
                break
    return backlinks


def get_wanted_slugs(session: Session) -> List[str]:
    """Return wiki-link targets that no page exists for yet ("wanted pages").

    Scans every concept body for ``[[...]]`` references and returns the set of
    targets that match neither a :class:`Concept` nor a :class:`SubConcept`,
    sorted alphabetically. Q-id-form targets (``[[Q...]]``) are skipped: they
    name a specific Wikidata entity rather than a creatable slug.

    Args:
        session: Database session.

    Returns:
        Sorted list of canonical slugs that are linked-to but missing.
    """
    existing: Set[str] = get_all_known_slugs(session)
    wanted: Set[str] = set()
    for concept in session.query(Concept).filter(Concept.body.isnot(None)):
        for link in parse_wiki_links(concept.body or ""):
            if not link.target_slug or link.target_slug in existing:
                continue
            if wiki_target_qid(link.target_slug):
                continue
            wanted.add(link.target_slug)
    return sorted(wanted)
