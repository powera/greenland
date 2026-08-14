"""The ``concept.persist`` stage of concept creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from concepts.validate import ConceptValidationResult, validate_seed
from storage.crud.concept import create_concept, link_wikidata_concept
from storage.models.concept import Concept
from storage.wikidata import WikidataConceptSeed

STAGE_NAME: str = "concept.persist"


@dataclass(frozen=True)
class ConceptCreationResult:
    """Outcome of a single create-from-Q-id attempt."""

    qid: str
    title: str
    concept: Optional[Concept]
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Return whether a concept was newly created."""
        return self.status == "created"


def result_from_validation(
    validation: ConceptValidationResult,
) -> ConceptCreationResult:
    """Convert a rejected validation result into the pipeline result type."""
    if validation.status is None:
        raise ValueError("accepted validation has no terminal result")
    return ConceptCreationResult(
        qid=validation.qid,
        title=validation.title,
        concept=validation.concept,
        status=validation.status,
        detail=validation.detail,
    )


def create_concept_from_seed(
    session: Session,
    seed: WikidataConceptSeed,
    *,
    body: str,
    source_model: Optional[str] = None,
    body_detail: str = "",
) -> ConceptCreationResult:
    """Validate and persist a concept from a previously acquired seed."""
    validation = validate_seed(session, seed)
    if not validation.accepted:
        return result_from_validation(validation)

    created_concept = create_concept(
        session,
        title=seed.title,
        summary=seed.summary,
        body=body,
        sources=list(seed.sources),
        source_model=source_model if body else None,
    )
    if created_concept is None:
        return ConceptCreationResult(
            qid=validation.qid,
            title=seed.title,
            concept=None,
            status="failed",
            detail="create_concept returned None",
        )

    link_wikidata_concept(session, validation.qid, created_concept)
    return ConceptCreationResult(
        qid=validation.qid,
        title=created_concept.title,
        concept=created_concept,
        status="created",
        detail=body_detail,
    )
