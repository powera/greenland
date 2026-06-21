#!/usr/bin/env python3
"""
Voverukas - Concept crawl ranker ("powering the crawl").

"Voverukas" means "little squirrel" in Lithuanian: it scampers across the
concept link-graph and decides which acorns to bury next. It complements
**Vovere** (the concept *generator*): Voverukas only ranks and reports, it
never creates or modifies concepts.

The agent runs the Voverukas ranking algorithm (a typed port of slmt's
"Powerrank") over every existing concept body, then surfaces the highest-ranked
"red links" -- ``[[wiki links]]`` whose target has no concept yet. That ranked
list is the worklist for which missing topics to create next: a red link cited
by many high-importance concepts ranks above one cited by a single obscure
concept.

This agent is READ-ONLY. It computes the ranking on the fly each run; nothing is
persisted.

Usage:
    PYTHONPATH=src python src/agents/voverukas.py --limit 30
    PYTHONPATH=src python src/agents/voverukas.py --limit 50 --iterations 6 --debug
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from storage.concept_service import create_concept_from_qid
from storage.crud.concept import cache_wikidata_title
from storage.models.concept import Concept, concept_slug_to_title
from storage.wikidata import resolve_titles_to_qids
from wordfreq.voverukas import (
    DEFAULT_DAMPING,
    DEFAULT_ITERATIONS,
    build_link_graph,
    compute_ranks,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class VoverukasAgent:
    """Read-only agent that ranks wanted (red-link) concept topics."""

    def __init__(self, config: DataSourceConfig) -> None:
        """Initialize the agent.

        Args:
            config: DataSourceConfig with backend and debug settings.
        """
        self.config = config
        self.debug = config.debug
        if self.debug:
            logger.setLevel(logging.DEBUG)

    def rank_wanted(
        self,
        *,
        limit: int = 50,
        iterations: int = DEFAULT_ITERATIONS,
        damping: float = DEFAULT_DAMPING,
    ) -> List[Dict[str, object]]:
        """Rank red-link targets by importance over the concept link-graph.

        Args:
            limit: Maximum number of wanted slugs to return.
            iterations: Number of ranking dispersion passes.
            damping: Fraction of a node's rank dispersed across its out-links.

        Returns:
            A list of ``{"slug", "title", "score", "inbound"}`` dicts for the
            top wanted (missing) topics, ordered by descending score.
        """
        session = create_backend_session(self.config)
        try:
            bodies_by_slug: Dict[str, str] = {}
            existing_slugs = set()
            for slug, body in session.query(Concept.slug, Concept.body).all():
                existing_slugs.add(slug)
                bodies_by_slug[slug] = body or ""

            logger.info("Loaded %d concepts", len(existing_slugs))

            link_graph, inbound_counts = build_link_graph(bodies_by_slug)
            ranks = compute_ranks(
                link_graph,
                existing_slugs,
                iterations=iterations,
                damping=damping,
            )

            # Keep only targets that are linked-to but have no concept yet.
            wanted: List[Dict[str, object]] = []
            for slug, score in ranks.top(n=len(ranks.scores)):
                if slug in existing_slugs:
                    continue
                wanted.append(
                    {
                        "slug": slug,
                        "title": concept_slug_to_title(slug),
                        "score": round(score, 4),
                        "inbound": inbound_counts.get(slug, 0),
                    }
                )
                if len(wanted) >= limit:
                    break
            return wanted
        finally:
            session.close()

    def _make_body_generator(self) -> Any:
        """Return a (title, summary, sources) -> body callable backed by Vovere.

        Imported lazily so ranking-only runs do not require the LLM client.
        """
        from agents.vovere import VovereAgent

        agent = VovereAgent(self.config)

        def generate(title: str, summary: str, sources: List[Dict[str, Any]]) -> str:
            return agent.generate_body(title, summary, sources)

        return generate

    def resolve_and_create(
        self,
        wanted: List[Dict[str, object]],
        *,
        create: bool,
        generate_body: bool,
    ) -> List[Dict[str, object]]:
        """Resolve ranked red-link titles to Q-ids (cached) and optionally create.

        Resolution uses a single batched Wikipedia API request for all titles.
        Every resolved Q-id is cached in ``concept_wikidata_index`` (title only,
        no concept yet). When ``create`` is set, each resolved Q-id is run
        through the shared concept-creation service.

        Args:
            wanted: Ranked wanted items from :meth:`rank_wanted`.
            create: If True, create a concept for each resolved Q-id.
            generate_body: If True (and creating), generate a Markdown body via
                Vovere; otherwise concepts are saved with sources but no body.

        Returns:
            ``wanted`` augmented in place with ``qid`` and (when creating)
            ``status``/``detail`` fields.
        """
        titles = [str(item["title"]) for item in wanted]
        qid_map = resolve_titles_to_qids(titles)

        body_generator = None
        if create and generate_body:
            body_generator = self._make_body_generator()

        session = create_backend_session(self.config)
        try:
            for item in wanted:
                qid = qid_map.get(str(item["title"]))
                item["qid"] = qid or ""
                if not qid:
                    if create:
                        item["status"] = "unresolved"
                    continue
                # Cache the qid<->title mapping regardless of creation.
                cache_wikidata_title(session, qid, str(item["title"]))
                if not create:
                    continue
                result = create_concept_from_qid(
                    session,
                    qid,
                    body_generator=body_generator,
                    source_model=self.config.model if body_generator else None,
                )
                item["status"] = result.status
                item["detail"] = result.detail
                logger.info(
                    "%s [%s] %s%s",
                    result.status.upper(),
                    qid,
                    item["title"],
                    f" - {result.detail}" if result.detail else "",
                )
            return wanted
        finally:
            session.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Voverukas - rank wanted (red-link) concept topics (read-only)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of ranked wanted topics to show (default: 50)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Number of ranking dispersion passes (default: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--damping",
        type=float,
        default=DEFAULT_DAMPING,
        help=f"Rank dispersed across out-links per pass (default: {DEFAULT_DAMPING})",
    )
    parser.add_argument(
        "--resolve-qids",
        action="store_true",
        help="Batch-resolve ranked titles to Wikidata Q-ids and cache them (read-only).",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a concept for each resolved Q-id (implies --resolve-qids).",
    )
    parser.add_argument(
        "--no-body",
        action="store_true",
        help="With --create, save concepts without generating an LLM body.",
    )
    add_common_args(parser)
    add_backend_args(parser)
    add_llm_args(parser)

    args = parser.parse_args()
    config = get_data_source_config(args)

    agent = VoverukasAgent(config)
    wanted = agent.rank_wanted(
        limit=args.limit,
        iterations=args.iterations,
        damping=args.damping,
    )

    if not wanted:
        logger.info("No wanted (red-link) topics found.")
        return 0

    if args.resolve_qids or args.create:
        if args.create and not args.yes:
            generate_note = "without bodies" if args.no_body else "with generated bodies"
            confirm = input(f"Create up to {len(wanted)} concepts {generate_note}? [y/N]: ")
            if confirm.strip().lower() != "y":
                logger.info("Aborted.")
                return 0
        wanted = agent.resolve_and_create(
            wanted,
            create=args.create,
            generate_body=not args.no_body,
        )

    show_qid = "qid" in wanted[0]
    show_status = "status" in wanted[0]
    header = f"{'#':>4}  {'score':>10}  {'inbound':>7}"
    if show_qid:
        header += f"  {'Q-id':>9}"
    if show_status:
        header += f"  {'status':>10}"
    header += "  topic"
    print(f"\nTop {len(wanted)} wanted concept topics (by Voverukas rank):\n")
    print(header)
    for index, item in enumerate(wanted, 1):
        row = f"{index:>4}  {item['score']:>10}  {item['inbound']:>7}"
        if show_qid:
            row += f"  {str(item.get('qid') or '—'):>9}"
        if show_status:
            row += f"  {str(item.get('status') or '—'):>10}"
        row += f"  {item['title']}"
        print(row)

    return 0


if __name__ == "__main__":
    sys.exit(main())
