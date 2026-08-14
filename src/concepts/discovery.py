"""Red-link discovery: rank the concept topics worth creating next.

Ranking runs the Voverukas algorithm (a typed port of slmt's "Powerrank") over
every existing concept body and surfaces the highest-ranked "red links" --
``[[wiki links]]`` whose target has no concept yet. Ranking itself is read-only
and computed on the fly; nothing is persisted.

The animal-named CLI (``agents/vovere/voverukas.py``) owns argument parsing,
confirmation, and table rendering; everything here is importable domain code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from concepts.pipeline import build_body_generator, create_concept_from_qid
from concepts.seed.qids import resolve_and_cache_title_qids
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.models.concept import (
    Concept,
    ConceptWikidataIndex,
    SubConcept,
    concept_slug_to_title,
    normalize_concept_slug,
    wiki_target_qid,
)
from wordfreq.voverukas import (
    DEFAULT_DAMPING,
    DEFAULT_ITERATIONS,
    build_link_graph,
    compute_ranks,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_DAMPING",
    "DEFAULT_ITERATIONS",
    "RankedTopic",
    "RankedTopics",
    "create_concepts_for_topics",
    "rank_wanted_topics",
    "resolve_topic_qids",
]

# Default number of ranked wanted topics returned by :func:`rank_wanted_topics`.
DEFAULT_WANTED_LIMIT: int = 50


@dataclass
class RankedTopic:
    """One ranked red-link topic, annotated as it moves through the pipeline."""

    slug: str
    title: str
    score: float
    inbound: int
    # Why the topic was kept out of the wanted list ("rejected", "sub-concept",
    # "excluded"); None for wanted topics.
    suppressed_reason: Optional[str] = None
    # Filled in by resolution ("" when the title resolves to no Q-id).
    qid: Optional[str] = None
    # Filled in by creation.
    status: Optional[str] = None
    detail: str = ""


@dataclass
class RankedTopics:
    """The wanted topics plus the ranked topics filtered out of that list."""

    wanted: List[RankedTopic] = field(default_factory=list)
    suppressed: List[RankedTopic] = field(default_factory=list)


def _triage_reasons_by_slug(session: Session) -> Dict[str, str]:
    """Map normalized remote titles to why their Q-id left the encyclopedia.

    Red links are matched through the cached remote title in
    ``concept_wikidata_index``, so a topic already rejected or filed as a
    sub-concept never re-enters the wanted list.
    """
    reasons: Dict[str, str] = {}
    for index_row in (
        session.query(ConceptWikidataIndex)
        .filter(ConceptWikidataIndex.title.isnot(None))
        .filter(
            ConceptWikidataIndex.rejected.is_(True)
            | ConceptWikidataIndex.sub_concept_id.isnot(None)
        )
        .all()
    ):
        if index_row.rejected:
            triage_reason = "rejected"
        elif index_row.sub_concept is not None and index_row.sub_concept.is_excluded:
            triage_reason = "excluded"
        else:
            triage_reason = "sub-concept"
        reasons[normalize_concept_slug(index_row.title or "")] = triage_reason
    return reasons


def rank_wanted_topics(
    config: DataSourceConfig,
    *,
    limit: int = DEFAULT_WANTED_LIMIT,
    iterations: int = DEFAULT_ITERATIONS,
    damping: float = DEFAULT_DAMPING,
) -> RankedTopics:
    """Rank red-link targets by importance over the concept link-graph.

    Sub-encyclopedia topics never rank as wanted: slugs present in
    ``sub_concepts`` count as existing, and red links whose cached Q-id is
    rejected or filed as a sub-concept are diverted to the suppressed list.
    Q-id-form targets (``[[Q...]]``) name a specific entity rather than a
    creatable slug and are skipped outright.

    Args:
        config: Backend and debug settings.
        limit: Maximum number of wanted topics to return.
        iterations: Number of ranking dispersion passes.
        damping: Fraction of a node's rank dispersed across its out-links.

    Returns:
        A :class:`RankedTopics` holding the top wanted (missing) topics ordered
        by descending score, plus the ranked topics that were filtered out.
    """
    session = create_backend_session(config)
    try:
        bodies_by_slug: Dict[str, str] = {}
        existing_slugs = set()
        for slug, body in session.query(Concept.slug, Concept.body).all():
            existing_slugs.add(slug)
            bodies_by_slug[slug] = body or ""

        sub_slugs = {row[0] for row in session.query(SubConcept.slug).all()}
        triage_reasons = _triage_reasons_by_slug(session)

        logger.info("Loaded %d concepts, %d sub-concepts", len(existing_slugs), len(sub_slugs))

        link_graph, inbound_counts = build_link_graph(bodies_by_slug)
        ranks = compute_ranks(
            link_graph,
            existing_slugs,
            iterations=iterations,
            damping=damping,
        )

        # Keep only targets that are linked-to but have no page yet.
        ranked = RankedTopics()
        for slug, score in ranks.top(n=len(ranks.scores)):
            if slug in existing_slugs or slug in sub_slugs:
                continue
            if wiki_target_qid(slug):
                continue
            topic = RankedTopic(
                slug=slug,
                title=concept_slug_to_title(slug),
                score=round(score, 4),
                inbound=inbound_counts.get(slug, 0),
                suppressed_reason=triage_reasons.get(slug),
            )
            if topic.suppressed_reason is not None:
                ranked.suppressed.append(topic)
                continue
            ranked.wanted.append(topic)
            if len(ranked.wanted) >= limit:
                break
        return ranked
    finally:
        session.close()


def resolve_topic_qids(
    config: DataSourceConfig, topics: List[RankedTopic]
) -> Dict[str, Optional[str]]:
    """Batch-resolve ranked titles to Q-ids, caching and annotating in place.

    Resolution uses a single batched Wikipedia API request for all titles, and
    every resolved Q-id is cached in ``concept_wikidata_index`` (title only, no
    concept yet).

    Args:
        config: Backend and debug settings.
        topics: Ranked topics from :func:`rank_wanted_topics`.

    Returns:
        The title -> Q-id (or None) map used to annotate ``topics``.
    """
    qid_map = resolve_and_cache_title_qids(config, [topic.title for topic in topics])
    for topic in topics:
        topic.qid = qid_map.get(topic.title) or ""
    return qid_map


def create_concepts_for_topics(
    config: DataSourceConfig,
    topics: List[RankedTopic],
    *,
    generate_body: bool,
) -> List[RankedTopic]:
    """Create a concept for each already-resolved topic Q-id.

    Args:
        config: Backend, model, and debug settings.
        topics: Ranked topics whose ``qid`` was filled in by
            :func:`resolve_topic_qids`.
        generate_body: If True, generate a Markdown body with the concept entry
            generator; otherwise concepts are saved with sources but no body.

    Returns:
        ``topics``, annotated in place with ``status`` and ``detail``.
    """
    body_generator = build_body_generator(config) if generate_body else None

    session = create_backend_session(config)
    try:
        for topic in topics:
            if not topic.qid:
                topic.status = "unresolved"
                continue
            result = create_concept_from_qid(
                session,
                topic.qid,
                body_generator=body_generator,
                source_model=config.model if body_generator else None,
                include_regional_wikis=True,
            )
            topic.status = result.status
            topic.detail = result.detail
            logger.info(
                "%s [%s] %s%s",
                result.status.upper(),
                topic.qid,
                topic.title,
                f" - {result.detail}" if result.detail else "",
            )
        return topics
    finally:
        session.close()
