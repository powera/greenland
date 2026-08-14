#!/usr/bin/env python3
"""
Voverukas - Concept crawl ranker ("powering the crawl").

"Voverukas" means "little squirrel" in Lithuanian: it scampers across the
concept link-graph and decides which acorns to bury next. It complements
**Vovere** (the concept *generator*): Voverukas only ranks and reports, it
never creates or modifies concepts.

The agent ranks every existing concept body's ``[[wiki links]]`` and surfaces
the highest-ranked "red links" -- targets with no concept yet. That ranked list
is the worklist for which missing topics to create next: a red link cited by
many high-importance concepts ranks above one cited by a single obscure
concept.

Ranking itself is READ-ONLY (computed on the fly each run, nothing persisted).
The optional ``--resolve-qids``/``--create``/``--batch`` steps do write (cached
Q-ids and, for create/batch, new concepts).

``--batch`` submits one OpenAI Batch job for all ranked topics at ~50% cost: it
fetches every concept's inputs (Wikidata seed + source text) up front, queues a
single batch, and the resulting bodies are turned into concepts later via
``agents/common/batch.py complete``.

This module is the command line only; the ranking, resolution, and batch logic
live in :mod:`concepts.discovery` and :mod:`concepts.generate.batch`.

Usage:
    PYTHONPATH=src python src/agents/vovere/voverukas.py --limit 30
    PYTHONPATH=src python src/agents/vovere/voverukas.py --limit 50 --iterations 6 --debug
    PYTHONPATH=src python src/agents/vovere/voverukas.py --limit 10 --batch --model gpt-5.4-mini
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List

# Add src directory to path (this file lives at src/agents/vovere/)
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from concepts.discovery import (
    DEFAULT_DAMPING,
    DEFAULT_ITERATIONS,
    RankedTopic,
    create_concepts_for_topics,
    rank_wanted_topics,
    resolve_topic_qids,
)
from concepts.generate.batch import ConceptBatchRequest, submit_concept_body_batch

# Agent name recorded on queued batch requests; the completion handler in
# agents/common/batch.py dispatches on this name.
BATCH_AGENT_NAME = "voverukas"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
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
        "--show-filtered",
        action="store_true",
        help=(
            "Also print ranked topics suppressed from the wanted list because "
            "their Q-id is rejected or filed as a sub-concept."
        ),
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
    parser.add_argument(
        "--batch",
        action="store_true",
        help=(
            "Fetch all inputs now and queue one OpenAI Batch job to generate every "
            "concept body (~50%% cheaper). Concepts are created later via "
            "'agents/common/batch.py complete'. Mutually exclusive with --create."
        ),
    )
    add_common_args(parser)
    add_backend_args(parser)
    add_llm_args(parser)
    return parser


def main() -> int:
    """Main entry point."""
    parser = get_argument_parser()
    args = parser.parse_args()

    if args.batch and args.create:
        parser.error("--batch and --create are mutually exclusive (batch creates later).")

    config = get_data_source_config(args)

    ranked = rank_wanted_topics(
        config,
        limit=args.limit,
        iterations=args.iterations,
        damping=args.damping,
    )

    if ranked.suppressed and not args.show_filtered:
        logger.info(
            "%d ranked topics suppressed (rejected / sub-concept); "
            "use --show-filtered to list them.",
            len(ranked.suppressed),
        )

    if not ranked.wanted:
        logger.info("No wanted (red-link) topics found.")
        if args.show_filtered and ranked.suppressed:
            _print_suppressed_table(ranked.suppressed)
        return 0

    if args.batch:
        # Resolve and show the exact topics + Q-ids before asking to submit.
        resolve_topic_qids(config, ranked.wanted)
        _print_wanted_table(ranked.wanted)
        resolvable = sum(1 for topic in ranked.wanted if topic.qid)
        if not args.yes:
            confirm = input(
                f"\nFetch inputs for {resolvable} resolved topics and submit one batch? [y/N]: "
            )
            if confirm.strip().lower() != "y":
                logger.info("Aborted.")
                return 0
        submission = submit_concept_body_batch(
            config,
            [ConceptBatchRequest(qid=topic.qid, title=topic.title) for topic in ranked.wanted],
            agent_name=BATCH_AGENT_NAME,
        )
        if not submission.batch_id:
            return 0
        print(
            f"\nSubmitted batch {submission.batch_id}: "
            f"{submission.queued} queued, {submission.skipped} skipped."
        )
        return 0

    if args.resolve_qids or args.create:
        if args.create and not args.yes:
            generate_note = "without bodies" if args.no_body else "with generated bodies"
            confirm = input(f"Create up to {len(ranked.wanted)} concepts {generate_note}? [y/N]: ")
            if confirm.strip().lower() != "y":
                logger.info("Aborted.")
                return 0
        resolve_topic_qids(config, ranked.wanted)
        if args.create:
            create_concepts_for_topics(
                config,
                ranked.wanted,
                generate_body=not args.no_body,
            )

    _print_wanted_table(ranked.wanted)
    if args.show_filtered and ranked.suppressed:
        _print_suppressed_table(ranked.suppressed)
    return 0


def _print_suppressed_table(suppressed: List[RankedTopic]) -> None:
    """Print ranked topics filtered out of the wanted list, with the reason."""
    print(f"\nSuppressed topics ({len(suppressed)}):\n")
    print(f"{'#':>4}  {'score':>10}  {'inbound':>7}  {'reason':>12}  topic")
    for index, topic in enumerate(suppressed, 1):
        print(
            f"{index:>4}  {topic.score:>10}  {topic.inbound:>7}"
            f"  {str(topic.suppressed_reason):>12}  {topic.title}"
        )


def _print_wanted_table(wanted: List[RankedTopic]) -> None:
    """Print the ranked wanted-topics table (score, inbound, Q-id, status)."""
    show_qid = any(topic.qid is not None for topic in wanted)
    show_status = any(topic.status is not None for topic in wanted)
    header = f"{'#':>4}  {'score':>10}  {'inbound':>7}"
    if show_qid:
        header += f"  {'Q-id':>9}"
    if show_status:
        header += f"  {'status':>10}"
    header += "  topic"
    print(f"\nTop {len(wanted)} wanted concept topics (by Voverukas rank):\n")
    print(header)
    for index, topic in enumerate(wanted, 1):
        row = f"{index:>4}  {topic.score:>10}  {topic.inbound:>7}"
        if show_qid:
            row += f"  {str(topic.qid or '—'):>9}"
        if show_status:
            row += f"  {str(topic.status or '—'):>10}"
        row += f"  {topic.title}"
        print(row)


if __name__ == "__main__":
    sys.exit(main())
