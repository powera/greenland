"""CRUD operations for the Concept model.

All slug handling goes through ``normalize_concept_slug`` so that space/underscore
variants of a title resolve to the same row (Wikipedia-style equivalence).
"""

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.models.concept import (
    ALL_SUB_CONCEPT_CATEGORIES,
    Concept,
    ConceptLemmaLink,
    ConceptWikidataIndex,
    MAX_CONCEPT_SOURCES,
    SubConcept,
    normalize_concept_slug,
)

if TYPE_CHECKING:
    from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def _normalize_sources(sources: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Serialize a list of source dicts to JSON, capped at MAX_CONCEPT_SOURCES.

    Args:
        sources: List of ``{"url": ..., "title": ..., "note": ...}`` dicts, or None.

    Returns:
        JSON string, or None if no sources were provided.
    """
    if not sources:
        return None
    return json.dumps(sources[:MAX_CONCEPT_SOURCES], ensure_ascii=False)


def get_wikidata_index(session: Session, qid: str) -> Optional[ConceptWikidataIndex]:
    """Return the Wikidata reverse-index row for a Q-id, if any."""
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return None
    return cast(
        Optional[ConceptWikidataIndex],
        session.query(ConceptWikidataIndex)
        .filter(ConceptWikidataIndex.qid == normalized_qid)
        .first(),
    )


def link_wikidata_concept(
    session: Session, qid: str, concept: Concept, *, notes: Optional[str] = None
) -> Optional[ConceptWikidataIndex]:
    """Create or update the reverse index linking a Wikidata Q-id to a concept.

    Refuses (returns None) when the Q-id already points at a sub-concept: the
    index targets are mutually exclusive, and repointing is an explicit
    promote/demote action, never a side effect of linking.
    """
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return None
    row = get_wikidata_index(session, normalized_qid)
    if row is not None and row.sub_concept_id is not None:
        logger.warning(
            "Refusing to link Q-id %s to concept %r: already filed as sub-concept %s",
            normalized_qid,
            concept.slug,
            row.sub_concept_id,
        )
        return None
    if row is None:
        row = ConceptWikidataIndex(qid=normalized_qid)
        session.add(row)
    row.concept = concept
    row.rejected = False
    if notes is not None:
        row.notes = notes
    try:
        session.commit()
        return row
    except IntegrityError as error:
        session.rollback()
        logger.warning("Failed to link Wikidata Q-id %s: %s", normalized_qid, error)
        return None


def cache_wikidata_title(session: Session, qid: str, title: str) -> Optional[ConceptWikidataIndex]:
    """Cache a Q-id and its remote Wikipedia title in the reverse index.

    Used for Q-ids that are known but have no concept yet (``concept_id`` stays
    NULL), e.g. ranked "wanted" red links resolved from titles. Existing rows
    keep their ``concept_id``/``rejected`` state; only the ``title`` is filled
    in (refreshed if a different title is supplied).

    Args:
        session: Database session.
        qid: A Wikidata Q-id (any case; normalized).
        title: The remote Wikipedia article title to cache.

    Returns:
        The cached/updated row, or None if the Q-id was invalid / the write
        failed.
    """
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return None
    clean_title = title.strip()
    if not clean_title:
        return None
    row = get_wikidata_index(session, normalized_qid)
    if row is None:
        row = ConceptWikidataIndex(qid=normalized_qid)
        session.add(row)
    row.title = clean_title
    try:
        session.commit()
        return row
    except IntegrityError as error:
        session.rollback()
        logger.warning("Failed to cache Wikidata title for %s: %s", normalized_qid, error)
        return None


def get_concept_by_slug(session: Session, slug: str) -> Optional[Concept]:
    """Look up a concept by slug, normalizing space/underscore equivalence.

    Args:
        session: Database session.
        slug: A title or wiki-link target ("Abraham Lincoln" or "Abraham_Lincoln").

    Returns:
        The matching Concept, or None if not found.
    """
    normalized = normalize_concept_slug(slug)
    return cast(
        Optional[Concept], session.query(Concept).filter(Concept.slug == normalized).first()
    )


def get_concept_by_id(session: Session, concept_id: int) -> Optional[Concept]:
    """Return a concept by its internal id, or None."""
    return cast(Optional[Concept], session.query(Concept).filter(Concept.id == concept_id).first())


def create_concept(
    session: Session,
    title: str,
    summary: Optional[str] = None,
    body: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    concept_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source_model: Optional[str] = None,
    confidence: float = 0.0,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Optional[Concept]:
    """Create a new concept.

    Args:
        session: Database session.
        title: Human-entered title; normalized to the canonical slug.
        summary: One-sentence description.
        body: Entry text (Markdown, may contain ``[[wiki links]]``).
        sources: Up to MAX_CONCEPT_SOURCES source dicts used as LLM input.
        concept_type: Coarse classification (e.g. "person", "event").
        tags: Free-form tags.
        source_model: Name of the LLM that authored the body, if any.
        confidence: LLM confidence (0-1).
        verified: Whether a human has reviewed it.
        notes: Optional notes.

    Returns:
        The created Concept, or None if the slug already exists / insert failed.
    """
    slug = normalize_concept_slug(title)
    if not slug:
        logger.warning("Refusing to create concept with empty title")
        return None

    concept = Concept(
        slug=slug,
        summary=summary,
        body=body,
        sources=_normalize_sources(sources),
        concept_type=concept_type,
        tags=json.dumps(tags, ensure_ascii=False) if tags else None,
        source_model=source_model,
        confidence=confidence,
        verified=verified,
        notes=notes,
    )
    try:
        session.add(concept)
        session.commit()
        logger.info(f"Created concept: {slug}")
        return concept
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Concept already exists or constraint violated for {slug!r}: {error}")
        return None


def update_concept(
    session: Session,
    concept: Concept,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    body: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    concept_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source_model: Optional[str] = None,
    confidence: Optional[float] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None,
) -> Optional[Concept]:
    """Update fields on an existing concept.

    Only non-None arguments are applied, except ``title``/``slug`` which is only
    changed when ``title`` is provided. Returns None (and rolls back) if the new
    slug collides with another concept.

    Args:
        session: Database session.
        concept: The concept to update.
        title: New title (re-normalized to a slug) if provided.
        summary: New one-sentence description.
        body: New entry text.
        sources: New source list (replaces existing).
        concept_type: New classification.
        tags: New tag list (replaces existing).
        source_model: New authoring-model name.
        confidence: New confidence value.
        verified: New verified flag.
        notes: New notes.

    Returns:
        The updated Concept, or None on slug collision.
    """
    if title is not None:
        concept.slug = normalize_concept_slug(title)
    if summary is not None:
        concept.summary = summary
    if body is not None:
        concept.body = body
    if sources is not None:
        concept.sources = _normalize_sources(sources)
    if concept_type is not None:
        concept.concept_type = concept_type
    if tags is not None:
        concept.tags = json.dumps(tags, ensure_ascii=False) if tags else None
    if source_model is not None:
        concept.source_model = source_model
    if confidence is not None:
        concept.confidence = confidence
    if verified is not None:
        concept.verified = verified
    if notes is not None:
        concept.notes = notes

    try:
        session.commit()
        logger.info(f"Updated concept: {concept.slug}")
        return concept
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Update collided with existing slug {concept.slug!r}: {error}")
        return None


def delete_concept(session: Session, concept: Concept) -> bool:
    """Delete a concept. Returns True if deleted."""
    session.delete(concept)
    session.commit()
    logger.info(f"Deleted concept: {concept.slug}")
    return True


# --- Sub-concepts ----------------------------------------------------------------
#
# Sub-encyclopedia entries: lightweight rows sharing the concepts' slug
# conventions and the Wikidata reverse index, but kept out of every
# main-encyclopedia code path. See storage.models.concept.SubConcept.


def get_sub_concept_by_slug(session: Session, slug: str) -> Optional[SubConcept]:
    """Look up a sub-concept by slug, normalizing space/underscore equivalence."""
    normalized = normalize_concept_slug(slug)
    return cast(
        Optional[SubConcept],
        session.query(SubConcept).filter(SubConcept.slug == normalized).first(),
    )


def get_sub_concept_by_id(session: Session, sub_concept_id: int) -> Optional[SubConcept]:
    """Return a sub-concept by its internal id, or None."""
    return cast(
        Optional[SubConcept],
        session.query(SubConcept).filter(SubConcept.id == sub_concept_id).first(),
    )


def create_sub_concept(
    session: Session,
    title: str,
    category: str,
    summary: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Optional[SubConcept]:
    """Create a new sub-concept.

    The slug may coexist with a main concept of the same slug (slug-based wiki
    links then resolve to the main concept; ``[[Q...]]`` links stay specific),
    but must be unique among sub-concepts.

    Args:
        session: Database session.
        title: Human-entered title; normalized to the canonical slug.
        category: One of ALL_SUB_CONCEPT_CATEGORIES (tracked, or strictly
            excluded like "micronation" to record that the topic is ignored).
        summary: One-sentence description.
        verified: Whether a human has reviewed it.
        notes: Optional notes (e.g. intake batch context).

    Returns:
        The created SubConcept, or None if the category is invalid, the slug is
        empty, or a sub-concept with the slug already exists.
    """
    if category not in ALL_SUB_CONCEPT_CATEGORIES:
        logger.warning("Refusing to create sub-concept with unknown category %r", category)
        return None
    slug = normalize_concept_slug(title)
    if not slug:
        logger.warning("Refusing to create sub-concept with empty title")
        return None

    sub_concept = SubConcept(
        slug=slug,
        category=category,
        summary=summary,
        verified=verified,
        notes=notes,
    )
    try:
        session.add(sub_concept)
        session.commit()
        logger.info(f"Created sub-concept: {slug} [{category}]")
        return sub_concept
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Sub-concept already exists or constraint violated for {slug!r}: {error}")
        return None


def update_sub_concept(
    session: Session,
    sub_concept: SubConcept,
    *,
    title: Optional[str] = None,
    category: Optional[str] = None,
    summary: Optional[str] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None,
) -> Optional[SubConcept]:
    """Update fields on an existing sub-concept.

    Only non-None arguments are applied. Returns None (and rolls back) if the
    new slug collides with another sub-concept or the category is invalid.
    """
    if category is not None:
        if category not in ALL_SUB_CONCEPT_CATEGORIES:
            logger.warning("Refusing to set unknown sub-concept category %r", category)
            return None
        sub_concept.category = category
    if title is not None:
        sub_concept.slug = normalize_concept_slug(title)
    if summary is not None:
        sub_concept.summary = summary
    if verified is not None:
        sub_concept.verified = verified
    if notes is not None:
        sub_concept.notes = notes

    try:
        session.commit()
        logger.info(f"Updated sub-concept: {sub_concept.slug}")
        return sub_concept
    except IntegrityError as error:
        session.rollback()
        logger.warning(f"Update collided with existing sub-concept {sub_concept.slug!r}: {error}")
        return None


def delete_sub_concept(session: Session, sub_concept: SubConcept) -> bool:
    """Delete a sub-concept, detaching any Wikidata index rows first."""
    session.query(ConceptWikidataIndex).filter(
        ConceptWikidataIndex.sub_concept_id == sub_concept.id
    ).update({ConceptWikidataIndex.sub_concept_id: None})
    session.delete(sub_concept)
    session.commit()
    logger.info(f"Deleted sub-concept: {sub_concept.slug}")
    return True


def link_wikidata_sub_concept(
    session: Session, qid: str, sub_concept: SubConcept, *, notes: Optional[str] = None
) -> Optional[ConceptWikidataIndex]:
    """Create or update the reverse index linking a Wikidata Q-id to a sub-concept.

    Mirror of :func:`link_wikidata_concept`. Refuses (returns None) when the
    Q-id already points at a main concept: repointing is an explicit
    promote/demote action, never a side effect of linking.
    """
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return None
    row = get_wikidata_index(session, normalized_qid)
    if row is not None and row.concept_id is not None:
        logger.warning(
            "Refusing to link Q-id %s to sub-concept %r: already linked to concept %s",
            normalized_qid,
            sub_concept.slug,
            row.concept_id,
        )
        return None
    if row is None:
        row = ConceptWikidataIndex(qid=normalized_qid)
        session.add(row)
    row.sub_concept = sub_concept
    row.rejected = False
    if notes is not None:
        row.notes = notes
    try:
        session.commit()
        return row
    except IntegrityError as error:
        session.rollback()
        logger.warning("Failed to link Wikidata Q-id %s to sub-concept: %s", normalized_qid, error)
        return None


def get_qids_for_sub_concept(session: Session, sub_concept_id: int) -> List[str]:
    """Return the Wikidata Q-ids linked to a sub-concept (usually 0 or 1)."""
    rows = (
        session.query(ConceptWikidataIndex.qid)
        .filter(ConceptWikidataIndex.sub_concept_id == sub_concept_id)
        .order_by(ConceptWikidataIndex.qid)
        .all()
    )
    return [row[0] for row in rows]


# --- Lemma <-> Concept pairing -------------------------------------------------
#
# A lemma links to at most one concept (by Q-id) and vice versa. The link lives
# with the lemmas (see ConceptLemmaLink) and stores the concept's Q-id directly,
# which is the only piece of concept data the data/release export consumes.
# Links are curated, not auto-created.


def get_link_for_lemma(session: Session, lemma_id: int) -> Optional[ConceptLemmaLink]:
    """Return the lemma<->concept link for a lemma, if one exists.

    Note: ``session`` must be the lemma/main DB session (where the
    ``concept_lemma_links`` table lives), not the concepts DB session.
    """
    return cast(
        Optional[ConceptLemmaLink],
        session.query(ConceptLemmaLink).filter(ConceptLemmaLink.lemma_id == lemma_id).first(),
    )


def get_link_for_qid(session: Session, qid: str) -> Optional[ConceptLemmaLink]:
    """Return the lemma<->concept link for a concept Q-id, if one exists."""
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return None
    return cast(
        Optional[ConceptLemmaLink],
        session.query(ConceptLemmaLink).filter(ConceptLemmaLink.qid == normalized_qid).first(),
    )


def link_lemma_to_concept(
    session: Session,
    lemma_id: int,
    qid: str,
    *,
    concept_slug: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Optional[ConceptLemmaLink]:
    """Pair a lemma with a concept Q-id (one-to-one on both sides).

    Idempotent for the same (lemma_id, qid) pair: re-linking updates
    ``concept_slug``/``verified``/``notes`` rather than failing. Returns None if
    either side is already linked to a *different* partner, the Q-id is invalid,
    or on any constraint failure (the caller should treat None as "left
    unlinked").

    Args:
        session: The lemma/main DB session (owns ``concept_lemma_links``).
        lemma_id: The lemma to link.
        qid: The Wikidata Q-id of the concept (any case; normalized).
        concept_slug: The concept's slug, stored for display.
        verified: Whether a human has confirmed the pairing.
        notes: Optional notes about the pairing.

    Returns:
        The created/updated link, or None if the pairing was rejected.
    """
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        logger.warning("Refusing to link lemma %s to invalid Q-id %r", lemma_id, qid)
        return None

    existing_for_lemma = get_link_for_lemma(session, lemma_id)
    existing_for_qid = get_link_for_qid(session, normalized_qid)

    if existing_for_lemma is not None and existing_for_lemma.qid == normalized_qid:
        # Same pair already linked: update metadata only.
        if concept_slug is not None:
            existing_for_lemma.concept_slug = concept_slug
        existing_for_lemma.verified = verified
        if notes is not None:
            existing_for_lemma.notes = notes
        try:
            session.commit()
            return existing_for_lemma
        except IntegrityError as error:
            session.rollback()
            logger.warning("Failed to update lemma-concept link: %s", error)
            return None

    if existing_for_lemma is not None:
        logger.warning(
            "Lemma %s already linked to %s; refusing to relink to %s",
            lemma_id,
            existing_for_lemma.qid,
            normalized_qid,
        )
        return None
    if existing_for_qid is not None:
        logger.warning(
            "Concept %s already linked to lemma %s; refusing to relink to %s",
            normalized_qid,
            existing_for_qid.lemma_id,
            lemma_id,
        )
        return None

    link = ConceptLemmaLink(
        lemma_id=lemma_id,
        qid=normalized_qid,
        concept_slug=concept_slug,
        verified=verified,
        notes=notes,
    )
    try:
        session.add(link)
        session.commit()
        logger.info("Linked lemma %s <-> concept %s", lemma_id, normalized_qid)
        return link
    except IntegrityError as error:
        session.rollback()
        logger.warning("Failed to link lemma %s to %s: %s", lemma_id, normalized_qid, error)
        return None


def unlink_lemma_from_concept(session: Session, *, lemma_id: int) -> bool:
    """Remove the lemma<->concept link for a lemma. Returns True if removed."""
    link = get_link_for_lemma(session, lemma_id)
    if link is None:
        return False
    session.delete(link)
    session.commit()
    logger.info("Unlinked lemma %s from concept %s", lemma_id, link.qid)
    return True


def get_qid_for_lemma(session: Session, lemma_id: int) -> Optional[str]:
    """Return the Wikidata Q-id paired with a lemma, if any.

    This is the single piece of concept data that flows into ``data/release``
    (e.g. "Apple" -> "Q89"). Returns None if the lemma is unlinked.
    """
    link = get_link_for_lemma(session, lemma_id)
    return link.qid if link is not None else None


def get_lemma_for_qid(session: Session, qid: str) -> Optional["Lemma"]:
    """Return the lemma paired with a concept Q-id, if any.

    The inverse of :func:`get_qid_for_lemma`: given a concept's Q-id (e.g.
    "Q89"), return the dictionary headword it names (e.g. the "apple" lemma).
    The Q-id is normalized, so any casing/whitespace is accepted. Returns None
    if the Q-id is invalid or unpaired.

    Note: ``session`` must be the lemma/main DB session (where both
    ``concept_lemma_links`` and ``lemmas`` live), not the concepts DB session.
    """
    from storage.models.schema import Lemma

    link = get_link_for_qid(session, qid)
    if link is None:
        return None
    return cast(
        Optional["Lemma"],
        session.query(Lemma).filter(Lemma.id == link.lemma_id).first(),
    )
