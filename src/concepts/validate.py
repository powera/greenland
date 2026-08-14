"""The ``concept.validate`` stage of concept creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from storage.crud.concept import get_concept_by_slug, get_wikidata_index
from storage.models.concept import Concept
from storage.wikidata import WikidataConceptSeed, normalize_qid

STAGE_NAME: str = "concept.validate"


@dataclass(frozen=True)
class ConceptValidationResult:
    """Result of checking whether a concept seed may be persisted."""

    qid: str
    title: str
    concept: Optional[Concept] = None
    status: Optional[str] = None
    detail: str = ""

    @property
    def accepted(self) -> bool:
        """Return whether pipeline processing may continue."""
        return self.status is None


def validate_qid(session: Session, qid: str) -> ConceptValidationResult:
    """Normalize a Q-id and reject invalid or already-filed identifiers."""
    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return ConceptValidationResult(qid=qid, title="", status="failed", detail="invalid Q-id")

    existing_index = get_wikidata_index(session, normalized_qid)
    if existing_index is not None and existing_index.concept is not None:
        existing_concept = existing_index.concept
        return ConceptValidationResult(
            qid=normalized_qid,
            title=existing_concept.title,
            concept=existing_concept,
            status="exists",
            detail=f"already linked to {existing_concept.slug!r}",
        )
    if existing_index is not None and existing_index.sub_concept is not None:
        sub_concept = existing_index.sub_concept
        filing = "strictly excluded" if sub_concept.is_excluded else "filed as sub-concept"
        return ConceptValidationResult(
            qid=normalized_qid,
            title=sub_concept.title,
            status="exists",
            detail=f"{filing} {sub_concept.slug!r} [{sub_concept.category}]",
        )

    return ConceptValidationResult(qid=normalized_qid, title="")


def validate_seed(session: Session, seed: WikidataConceptSeed) -> ConceptValidationResult:
    """Reject an invalid, already-filed, or duplicate-title concept seed."""
    qid_validation = validate_qid(session, seed.qid)
    if not qid_validation.accepted:
        return qid_validation

    if get_concept_by_slug(session, seed.title) is not None:
        return ConceptValidationResult(
            qid=qid_validation.qid,
            title=seed.title,
            status="exists",
            detail=f"a concept titled {seed.title!r} already exists",
        )

    return ConceptValidationResult(qid=qid_validation.qid, title=seed.title)
