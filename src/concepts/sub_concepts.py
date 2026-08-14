"""Sub-concept filing, promotion, and demotion workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from storage.crud.concept import (
    create_concept,
    create_sub_concept,
    get_concept_by_slug,
    get_sub_concept_by_slug,
    get_wikidata_index,
    link_wikidata_sub_concept,
)
from storage.models.concept import Concept, ConceptWikidataIndex, SubConcept
from storage.wikidata import fetch_wikidata_concept_seed, normalize_qid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubConceptFilingResult:
    """Outcome of a single file-as-sub-concept attempt."""

    qid: str
    title: str
    sub_concept: Optional[SubConcept]
    status: str  # "filed" | "exists" | "unresolved" | "failed"
    detail: str = ""

    @property
    def ok(self) -> bool:
        """True when a sub-concept was newly filed."""
        return self.status == "filed"


def file_sub_concept_from_qid(
    session: Session,
    qid: str,
    category: str,
    *,
    notes: Optional[str] = None,
) -> SubConceptFilingResult:
    """File a Wikidata Q-id into the sub-encyclopedia (seed -> create -> link).

    No LLM is involved: the row is built from the Wikidata seed's title and
    summary only. Idempotent: a Q-id already pointing at a concept or a
    sub-concept is reported as "exists" and left untouched.

    Args:
        session: Database session (concepts backend).
        qid: A Wikidata Q-id (any case; normalized).
        category: One of ALL_SUB_CONCEPT_CATEGORIES. A strictly excluded
            category (e.g. "micronation") actively records that the Q-id is
            ignored rather than deferred.
        notes: Optional notes (e.g. intake batch context).

    Returns:
        A :class:`SubConceptFilingResult` describing the outcome.
    """
    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return SubConceptFilingResult(
            qid=qid, title="", sub_concept=None, status="failed", detail="invalid Q-id"
        )

    existing_index = get_wikidata_index(session, normalized_qid)
    if existing_index is not None and existing_index.sub_concept is not None:
        sub = existing_index.sub_concept
        return SubConceptFilingResult(
            qid=normalized_qid,
            title=sub.title,
            sub_concept=sub,
            status="exists",
            detail=f"already filed as {sub.slug!r} [{sub.category}]",
        )
    if existing_index is not None and existing_index.concept is not None:
        concept = existing_index.concept
        return SubConceptFilingResult(
            qid=normalized_qid,
            title=concept.title,
            sub_concept=None,
            status="exists",
            detail=f"already a main concept {concept.slug!r}",
        )

    seed = fetch_wikidata_concept_seed(normalized_qid)
    if seed is None:
        return SubConceptFilingResult(
            qid=normalized_qid,
            title="",
            sub_concept=None,
            status="unresolved",
            detail="Wikidata seed could not be resolved",
        )

    if get_sub_concept_by_slug(session, seed.title) is not None:
        return SubConceptFilingResult(
            qid=normalized_qid,
            title=seed.title,
            sub_concept=None,
            status="exists",
            detail=f"a sub-concept titled {seed.title!r} already exists",
        )

    created = create_sub_concept(
        session,
        title=seed.title,
        category=category,
        summary=seed.summary,
        notes=notes,
    )
    if created is None:
        return SubConceptFilingResult(
            qid=normalized_qid,
            title=seed.title,
            sub_concept=None,
            status="failed",
            detail="create_sub_concept returned None",
        )

    link_wikidata_sub_concept(session, normalized_qid, created)
    detail = ""
    if get_concept_by_slug(session, created.slug) is not None:
        detail = "slug also exists as a main concept; slug links resolve there"
    return SubConceptFilingResult(
        qid=normalized_qid,
        title=created.title,
        sub_concept=created,
        status="filed",
        detail=detail,
    )


def promote_sub_concept(session: Session, sub_concept: SubConcept) -> Optional[Concept]:
    """Promote a sub-concept to a main concept, repointing its Q-ids.

    Creates a main :class:`Concept` from the sub-concept's slug/summary/notes
    (no body -- generate later), moves every Wikidata index row from the
    sub-concept to the new concept, and deletes the sub-concept row so the
    slug and Q-id never exist on both sides.

    Strictly excluded sub-concepts (e.g. category "micronation") cannot be
    promoted: the exclusion is the point of the row. Move the sub-concept to
    a tracked category first if the judgement has genuinely changed.

    Returns:
        The new Concept, or None if the sub-concept is strictly excluded or a
        main concept with the slug already exists (the sub-concept is left
        untouched).
    """
    if sub_concept.is_excluded:
        logger.warning(
            "Refusing to promote strictly excluded sub-concept %r [%s]",
            sub_concept.slug,
            sub_concept.category,
        )
        return None
    concept = create_concept(
        session,
        title=sub_concept.slug,
        summary=sub_concept.summary,
        notes=sub_concept.notes,
        verified=sub_concept.verified,
    )
    if concept is None:
        logger.warning(
            "Cannot promote sub-concept %r: a main concept with that slug exists",
            sub_concept.slug,
        )
        return None
    session.query(ConceptWikidataIndex).filter(
        ConceptWikidataIndex.sub_concept_id == sub_concept.id
    ).update(
        {
            ConceptWikidataIndex.sub_concept_id: None,
            ConceptWikidataIndex.concept_id: concept.id,
        }
    )
    session.delete(sub_concept)
    session.commit()
    logger.info("Promoted sub-concept %r to main concept", concept.slug)
    return concept


def demote_concept_to_sub(
    session: Session, concept: Concept, category: str
) -> Optional[SubConcept]:
    """Demote a main concept to a sub-concept, repointing its Q-ids.

    The mirror of :func:`promote_sub_concept`. The concept's body and sources
    are DISCARDED (sub-concepts carry neither); callers must confirm that loss
    explicitly before invoking this.

    Returns:
        The new SubConcept, or None if the category is invalid or a
        sub-concept with the slug already exists (the concept is left
        untouched).
    """
    sub_concept = create_sub_concept(
        session,
        title=concept.slug,
        category=category,
        summary=concept.summary,
        verified=concept.verified,
        notes=concept.notes,
    )
    if sub_concept is None:
        logger.warning("Cannot demote concept %r to sub-concept", concept.slug)
        return None
    session.query(ConceptWikidataIndex).filter(
        ConceptWikidataIndex.concept_id == concept.id
    ).update(
        {
            ConceptWikidataIndex.concept_id: None,
            ConceptWikidataIndex.sub_concept_id: sub_concept.id,
        }
    )
    session.delete(concept)
    session.commit()
    logger.info("Demoted concept %r to sub-concept [%s]", sub_concept.slug, category)
    return sub_concept
