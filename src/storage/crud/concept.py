"""CRUD operations for the Concept model.

All slug handling goes through ``normalize_concept_slug`` so that space/underscore
variants of a title resolve to the same row (Wikipedia-style equivalence).
"""

import json
import logging
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from storage.models.concept import (
    Concept,
    ConceptWikidataIndex,
    MAX_CONCEPT_SOURCES,
    normalize_concept_slug,
)

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
    """Create or update the reverse index linking a Wikidata Q-id to a concept."""
    from storage.wikidata import normalize_qid

    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return None
    row = get_wikidata_index(session, normalized_qid)
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
