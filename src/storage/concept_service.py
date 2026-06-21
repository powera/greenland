"""Service helpers that orchestrate concept creation across storage + Wikidata.

This sits above the thin CRUD layer (:mod:`storage.crud.concept`) and the
Wikidata client (:mod:`storage.wikidata`). It owns the multi-step "create a
concept from a Wikidata Q-id" flow so both the Barsukas route and bulk agents
(e.g. ``voverukas``) share one implementation instead of duplicating it.

Body generation is injected as a callable so this module stays decoupled from
the LLM/agents layer: callers that can generate a body pass a ``body_generator``;
callers that cannot (or run with outbound calls disabled) omit it and the
concept is saved with an empty body.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from storage.crud.concept import (
    create_concept,
    get_concept_by_slug,
    get_wikidata_index,
    link_wikidata_concept,
)
from storage.models.concept import Concept
from storage.wikidata import fetch_wikidata_concept_seed, normalize_qid

logger = logging.getLogger(__name__)

# A body generator takes (title, summary, sources) and returns Markdown.
BodyGenerator = Callable[[str, str, List[Dict[str, Any]]], str]


@dataclass(frozen=True)
class ConceptCreationResult:
    """Outcome of a single create-from-Q-id attempt."""

    qid: str
    title: str
    concept: Optional[Concept]
    status: str  # "created" | "exists" | "unresolved" | "failed"
    detail: str = ""

    @property
    def ok(self) -> bool:
        """True when a concept was newly created."""
        return self.status == "created"


def create_concept_from_qid(
    session: Session,
    qid: str,
    *,
    body_generator: Optional[BodyGenerator] = None,
    source_model: Optional[str] = None,
    include_regional_wikis: bool = False,
) -> ConceptCreationResult:
    """Create a concept from a Wikidata Q-id (seed -> body -> create -> link).

    Idempotent: if the Q-id is already linked to a concept, or a concept with
    the seeded title already exists, no new concept is created.

    Args:
        session: Database session.
        qid: A Wikidata Q-id (any case; normalized).
        body_generator: Optional callable that turns (title, summary, sources)
            into a Markdown body. If omitted, the concept is saved with an empty
            body (sources are still stored for later generation).
        source_model: Name of the model used by ``body_generator``, recorded on
            the concept when a body is successfully generated.
        include_regional_wikis: Pass through to the Wikidata seed fetch.

    Returns:
        A :class:`ConceptCreationResult` describing the outcome.
    """
    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return ConceptCreationResult(
            qid=qid, title="", concept=None, status="failed", detail="invalid Q-id"
        )

    existing_index = get_wikidata_index(session, normalized_qid)
    if existing_index is not None and existing_index.concept is not None:
        concept = existing_index.concept
        return ConceptCreationResult(
            qid=normalized_qid,
            title=concept.title,
            concept=concept,
            status="exists",
            detail=f"already linked to {concept.slug!r}",
        )

    seed = fetch_wikidata_concept_seed(
        normalized_qid, include_regional_wikis=include_regional_wikis
    )
    if seed is None:
        return ConceptCreationResult(
            qid=normalized_qid,
            title="",
            concept=None,
            status="unresolved",
            detail="Wikidata seed could not be resolved",
        )

    if get_concept_by_slug(session, seed.title) is not None:
        return ConceptCreationResult(
            qid=normalized_qid,
            title=seed.title,
            concept=None,
            status="exists",
            detail=f"a concept titled {seed.title!r} already exists",
        )

    body = ""
    body_model: Optional[str] = None
    return_detail = ""
    if body_generator is not None:
        try:
            body = body_generator(seed.title, seed.summary, list(seed.sources))
            body_model = source_model
        except Exception as exc:  # generation failure must not lose the entry
            logger.exception("Concept body generation failed for %s", normalized_qid)
            body = ""
            return_detail = f"saved without body: {exc}"
    else:
        return_detail = "no body generator supplied"

    created = create_concept(
        session,
        title=seed.title,
        summary=seed.summary,
        body=body,
        sources=list(seed.sources),
        source_model=body_model,
    )
    if created is None:
        return ConceptCreationResult(
            qid=normalized_qid,
            title=seed.title,
            concept=None,
            status="failed",
            detail="create_concept returned None",
        )

    link_wikidata_concept(session, normalized_qid, created)
    return ConceptCreationResult(
        qid=normalized_qid,
        title=created.title,
        concept=created,
        status="created",
        detail=return_detail,
    )
