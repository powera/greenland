"""Service helpers that orchestrate text-work creation across storage + Wikidata.

Mirror of :mod:`storage.concept_service` for the story library: owns the
"create a text work from a Wikidata Q-id" flow (seed fetch -> create) so the
Barsukas route and any future bulk intake share one implementation. No body
generation happens here -- versions are added separately (Ožys for authored
works, transcription for canonical ones).

Per project policy, flows that resolve Q-ids make live Wikidata/Wikipedia API
calls and need developer confirmation before running in bulk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from storage.crud.text_work import create_text_work, get_text_work_by_qid, get_text_work_by_slug
from storage.models.text_work import (
    ALL_TEXT_TYPES,
    TextWork,
    is_intake_deferred_text_type,
)
from storage.wikidata import fetch_wikidata_concept_seed, normalize_qid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextWorkCreationResult:
    """Outcome of a single create-work-from-Q-id attempt."""

    qid: str
    title: str
    work: Optional[TextWork]
    status: str  # "created" | "exists" | "unresolved" | "failed"
    detail: str = ""

    @property
    def ok(self) -> bool:
        """True when a work was newly created."""
        return self.status == "created"


def create_text_work_from_qid(
    session: Session,
    qid: str,
    text_type: str,
    *,
    attribution_qid: Optional[str] = None,
    attribution: Optional[str] = None,
    notes: Optional[str] = None,
) -> TextWorkCreationResult:
    """Create a text work from a Wikidata Q-id (seed -> create; no versions).

    Idempotent: if a work with this Q-id already exists, or a work with the
    seeded title already exists, no new work is created.

    Args:
        session: Database session (concepts backend).
        qid: The work's own Wikidata Q-id (any case; normalized).
        text_type: One of ALL_TEXT_TYPES (intake-deferred types are refused).
        attribution_qid: Optional Q-id of the attributed person/source.
        attribution: Optional display attribution line.
        notes: Optional notes (e.g. curation context).

    Returns:
        A :class:`TextWorkCreationResult` describing the outcome.
    """
    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        return TextWorkCreationResult(
            qid=qid, title="", work=None, status="failed", detail="invalid Q-id"
        )
    if text_type not in ALL_TEXT_TYPES:
        return TextWorkCreationResult(
            qid=normalized_qid,
            title="",
            work=None,
            status="failed",
            detail=f"unknown text type {text_type!r}",
        )
    if is_intake_deferred_text_type(text_type):
        return TextWorkCreationResult(
            qid=normalized_qid,
            title="",
            work=None,
            status="failed",
            detail=f"text type {text_type!r} has no intake yet",
        )

    logger.debug(
        "create_text_work_from_qid: qid=%s (raw=%r) text_type=%s attribution_qid=%s",
        normalized_qid,
        qid,
        text_type,
        attribution_qid,
    )

    existing = get_text_work_by_qid(session, normalized_qid)
    if existing is not None:
        logger.debug(
            "create_text_work_from_qid: %s already exists as slug=%r id=%s; no Wikidata fetch",
            normalized_qid,
            existing.slug,
            existing.id,
        )
        return TextWorkCreationResult(
            qid=normalized_qid,
            title=existing.title,
            work=existing,
            status="exists",
            detail=f"already in the library as {existing.slug!r} [{existing.text_type}]",
        )

    logger.debug(
        "create_text_work_from_qid: fetching Wikidata/Wikipedia seed for %s", normalized_qid
    )
    seed = fetch_wikidata_concept_seed(normalized_qid)
    if seed is None:
        logger.debug("create_text_work_from_qid: %s did not resolve to a seed", normalized_qid)
        return TextWorkCreationResult(
            qid=normalized_qid,
            title="",
            work=None,
            status="unresolved",
            detail="Wikidata seed could not be resolved",
        )
    logger.debug(
        "create_text_work_from_qid: %s resolved to title=%r summary=%r (%d source(s): %s)",
        normalized_qid,
        seed.title,
        seed.summary,
        len(seed.sources),
        ", ".join(str(s.get("url", "?")) for s in seed.sources) or "none",
    )

    if get_text_work_by_slug(session, seed.title) is not None:
        logger.debug(
            "create_text_work_from_qid: seeded title %r collides with an existing work",
            seed.title,
        )
        return TextWorkCreationResult(
            qid=normalized_qid,
            title=seed.title,
            work=None,
            status="exists",
            detail=f"a work titled {seed.title!r} already exists",
        )

    created = create_text_work(
        session,
        title=seed.title,
        text_type=text_type,
        qid=normalized_qid,
        attribution_qid=attribution_qid,
        attribution=attribution,
        summary=seed.summary,
        notes=notes,
    )
    if created is None:
        logger.debug(
            "create_text_work_from_qid: create_text_work returned None for title=%r", seed.title
        )
        return TextWorkCreationResult(
            qid=normalized_qid,
            title=seed.title,
            work=None,
            status="failed",
            detail="create_text_work returned None",
        )

    logger.debug(
        "create_text_work_from_qid: created work id=%s slug=%r title=%r type=%s qid=%s "
        "summary=%r (no versions yet)",
        created.id,
        created.slug,
        created.title,
        created.text_type,
        created.qid,
        created.summary,
    )
    return TextWorkCreationResult(
        qid=normalized_qid,
        title=created.title,
        work=created,
        status="created",
    )
