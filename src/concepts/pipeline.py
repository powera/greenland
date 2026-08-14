"""Pipeline for building a concept from a Wikidata Q-id."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from concepts.persist import (
    ConceptCreationResult,
    create_concept_from_seed,
    result_from_validation,
)
from concepts.seed.wikidata_query import query_wikidata_seed
from concepts.validate import validate_qid, validate_seed
from storage.backend.config import DataSourceConfig

logger = logging.getLogger(__name__)

BodyGenerator = Callable[[str, str, List[Dict[str, Any]]], str]


def build_body_generator(config: DataSourceConfig) -> BodyGenerator:
    """Return a ``(title, summary, sources) -> body`` callable backed by an LLM.

    The generator is imported lazily so read-only runs (ranking, resolution)
    never need to construct an LLM client.
    """
    from concepts.generate.entry import ConceptEntryGenerator

    generator = ConceptEntryGenerator(config)

    def generate(title: str, summary: str, sources: List[Dict[str, Any]]) -> str:
        return generator.generate_body(title, summary, sources)

    return generate


def create_concept_from_qid(
    session: Session,
    qid: str,
    *,
    body_generator: Optional[BodyGenerator] = None,
    source_model: Optional[str] = None,
    include_regional_wikis: bool = False,
) -> ConceptCreationResult:
    """Run seed query, entry generation, validation, and persistence."""
    initial_validation = validate_qid(session, qid)
    if not initial_validation.accepted:
        return result_from_validation(initial_validation)

    seed = query_wikidata_seed(
        initial_validation.qid,
        include_regional_wikis=include_regional_wikis,
    )
    if seed is None:
        return ConceptCreationResult(
            qid=initial_validation.qid,
            title="",
            concept=None,
            status="unresolved",
            detail="Wikidata seed could not be resolved",
        )

    body = ""
    body_model: Optional[str] = None
    body_detail = ""
    if body_generator is None:
        body_detail = "no body generator supplied"
    else:
        try:
            body = body_generator(seed.title, seed.summary, list(seed.sources))
            body_model = source_model
        except Exception as error:  # generation failure must not lose the entry
            logger.exception("Concept body generation failed for %s", initial_validation.qid)
            body_detail = f"saved without body: {error}"

    seed_validation = validate_seed(session, seed)
    if not seed_validation.accepted:
        return result_from_validation(seed_validation)

    return create_concept_from_seed(
        session,
        seed,
        body=body,
        source_model=body_model,
        body_detail=body_detail,
    )
