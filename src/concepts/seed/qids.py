"""Q-id intake: resolve Wikidata Q-ids and turn them into concept rows.

Two entry paths land here:

* an explicit, hand-picked list of Q-ids (``agents/vovere/voveraite.py``), and
* titles discovered by red-link ranking, resolved to Q-ids in one batched
  Wikipedia request (``concepts.discovery``).

Both share the same idempotent creation and sub-concept filing services, so a
Q-id already linked to a concept or a sub-concept is reported and skipped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from concepts.pipeline import build_body_generator, create_concept_from_qid
from concepts.seed.wikidata_query import query_wikidata_seed
from concepts.sub_concepts import file_sub_concept_from_qid
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.crud.concept import cache_wikidata_title
from storage.wikidata import normalize_qid, resolve_titles_to_qids

logger = logging.getLogger(__name__)

__all__ = [
    "QidIntakeResult",
    "QidResolution",
    "create_concepts_from_qids",
    "file_sub_concepts_from_qids",
    "resolve_and_cache_title_qids",
    "resolve_qids",
]


@dataclass(frozen=True)
class QidResolution:
    """Outcome of looking one Q-id up on Wikidata (no writes involved)."""

    qid: str
    title: str
    resolved: bool


@dataclass(frozen=True)
class QidIntakeResult:
    """Outcome of filing one Q-id as a concept or a sub-concept."""

    qid: str
    title: str
    status: str
    detail: str = ""


def resolve_qids(qids: Sequence[str]) -> List[QidResolution]:
    """Fetch each Q-id's Wikidata seed and report it without writing anything.

    Args:
        qids: Wikidata Q-ids (any case; normalized here).

    Returns:
        One :class:`QidResolution` per input Q-id, in the input order.
    """
    resolutions: List[QidResolution] = []
    for raw_qid in qids:
        qid = normalize_qid(raw_qid)
        if qid is None:
            logger.info("INVALID %s", raw_qid)
            resolutions.append(QidResolution(qid=raw_qid, title="", resolved=False))
            continue
        seed = query_wikidata_seed(qid)
        if seed is None:
            logger.info("UNRESOLVED [%s]", qid)
            resolutions.append(QidResolution(qid=qid, title="", resolved=False))
            continue
        logger.info("RESOLVED [%s] %s", qid, seed.title)
        resolutions.append(QidResolution(qid=qid, title=seed.title, resolved=True))
    return resolutions


def resolve_and_cache_title_qids(
    config: DataSourceConfig, titles: Sequence[str]
) -> Dict[str, Optional[str]]:
    """Resolve titles to Q-ids in one batched request and cache the mappings.

    Args:
        config: Backend and debug settings.
        titles: Wikipedia-style titles to resolve.

    Returns:
        A title -> Q-id (or None) map.
    """
    qid_map = resolve_titles_to_qids(list(titles))

    session = create_backend_session(config)
    try:
        for title, qid in qid_map.items():
            if qid:
                cache_wikidata_title(session, qid, title)
    finally:
        session.close()
    return qid_map


def create_concepts_from_qids(
    config: DataSourceConfig,
    qids: Sequence[str],
    *,
    generate_body: bool,
) -> List[QidIntakeResult]:
    """Create a concept for each Q-id via the shared concept pipeline.

    Args:
        config: Backend, model, and debug settings.
        qids: Wikidata Q-ids (any case; normalized by the pipeline).
        generate_body: If True, generate a Markdown body with the concept entry
            generator; otherwise concepts are saved with sources but no body.

    Returns:
        One :class:`QidIntakeResult` per Q-id, in the input order.
    """
    body_generator = build_body_generator(config) if generate_body else None

    results: List[QidIntakeResult] = []
    session = create_backend_session(config)
    try:
        for raw_qid in qids:
            result = create_concept_from_qid(
                session,
                raw_qid,
                body_generator=body_generator,
                source_model=config.model if body_generator else None,
                include_regional_wikis=True,
            )
            results.append(
                QidIntakeResult(
                    qid=result.qid,
                    title=result.title,
                    status=result.status,
                    detail=result.detail,
                )
            )
            logger.info(
                "%s [%s] %s%s",
                result.status.upper(),
                result.qid,
                result.title,
                f" - {result.detail}" if result.detail else "",
            )
        return results
    finally:
        session.close()


def file_sub_concepts_from_qids(
    config: DataSourceConfig,
    qids: Sequence[str],
    category: str,
) -> List[QidIntakeResult]:
    """File each Q-id into the sub-encyclopedia via the shared service.

    No LLM is involved: each row is built from the Wikidata seed alone.

    Args:
        config: Backend and debug settings.
        qids: Wikidata Q-ids (any case; normalized by the service).
        category: One of ``ALL_SUB_CONCEPT_CATEGORIES``, applied to every Q-id.

    Returns:
        One :class:`QidIntakeResult` per Q-id, in the input order.
    """
    results: List[QidIntakeResult] = []
    session = create_backend_session(config)
    try:
        for raw_qid in qids:
            result = file_sub_concept_from_qid(session, raw_qid, category)
            results.append(
                QidIntakeResult(
                    qid=result.qid,
                    title=result.title,
                    status=result.status,
                    detail=result.detail,
                )
            )
            logger.info(
                "%s [%s] %s%s",
                result.status.upper(),
                result.qid,
                result.title,
                f" - {result.detail}" if result.detail else "",
            )
        return results
    finally:
        session.close()
