#!/usr/bin/env python3
"""
Voveraite - create concepts from an explicit list of Wikidata Q-ids.

"Voveraite" is another "little squirrel" diminutive, kin to **Vovere** (the
concept *generator*) and **Voverukas** (the red-link *ranker*). Where Voverukas
*discovers* topics by ranking red links, Voveraite takes a hand-picked list of
Wikidata Q-ids and turns each into a concept. It reuses the family's plumbing --
the shared Q-id concept service, the concept body generator, and the OpenAI
Batch queue -- but skips ranking and title->Q-id resolution entirely, since the
Q-ids are given.

Modes:
    --batch   Queue one OpenAI Batch job for every Q-id's body (~50% cheaper).
              Concepts are created later via ``agents/common/batch.py complete``.
    --create  Create each concept inline now (one LLM call per Q-id), or with
              --no-body save sources without generating a body.
    --sub     File each Q-id into the sub-encyclopedia (requires --category).
              Creates lightweight SubConcept rows from the Wikidata seed; no
              LLM calls are involved.
    (default) Resolve + report each Q-id's seed without writing anything.

Concept creation is idempotent: a Q-id already linked to a concept or a
sub-concept (or whose seeded title already exists) is skipped.

This module is the command line only; resolution and intake live in
:mod:`concepts.seed.qids`, batch submission in :mod:`concepts.generate.batch`.

Usage:
    PYTHONPATH=src python src/agents/vovere/voveraite.py Q8768 Q8743 Q8704
    PYTHONPATH=src python src/agents/vovere/voveraite.py Q8768 Q8743 --create --model gpt-5.4-mini
    PYTHONPATH=src python src/agents/vovere/voveraite.py Q8768 Q8743 --batch --model gpt-5.4-mini
    PYTHONPATH=src python src/agents/vovere/voveraite.py Q103632 --sub --category chess_concept
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
from concepts.generate.batch import ConceptBatchRequest, submit_concept_body_batch
from concepts.seed.qids import (
    QidResolution,
    create_concepts_from_qids,
    file_sub_concepts_from_qids,
    resolve_qids,
)
from storage.models.concept import ALL_SUB_CONCEPT_CATEGORIES

# Agent name recorded on queued batch requests; the completion handler in
# agents/common/batch.py dispatches on this name.
BATCH_AGENT_NAME = "voveraite"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _print_resolution(resolved: List[QidResolution]) -> None:
    """Print a Q-id -> title table for resolved (and unresolved) Q-ids."""
    print(f"\n{'Q-id':<12} {'Status':<12} Title")
    print("-" * 60)
    for item in resolved:
        status = "resolved" if item.resolved else "UNRESOLVED"
        print(f"{item.qid:<12} {status:<12} {item.title}")
    n_ok = sum(1 for item in resolved if item.resolved)
    print(f"\n{n_ok}/{len(resolved)} Q-ids resolved.")


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Voveraite - create concepts from explicit Wikidata Q-ids"
    )
    parser.add_argument(
        "qids",
        nargs="+",
        metavar="QID",
        help="Wikidata Q-ids to create concepts for (e.g. Q8768 Q8743).",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a concept for each Q-id now (one LLM call per Q-id).",
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
            "Queue one OpenAI Batch job to generate every concept body "
            "(~50%% cheaper). Concepts are created later via "
            "'agents/common/batch.py complete'. Mutually exclusive with --create."
        ),
    )
    parser.add_argument(
        "--sub",
        action="store_true",
        help=(
            "File each Q-id into the sub-encyclopedia instead of creating "
            "concepts (no LLM). Requires --category."
        ),
    )
    parser.add_argument(
        "--category",
        choices=ALL_SUB_CONCEPT_CATEGORIES,
        help=(
            "Sub-concept category applied to every Q-id (with --sub). Strictly "
            "excluded categories (e.g. micronation) record that the Q-ids are "
            "deliberately ignored."
        ),
    )
    add_common_args(parser)
    add_backend_args(parser)
    add_llm_args(parser)
    return parser


def main() -> int:
    parser = get_argument_parser()
    args = parser.parse_args()

    if args.batch and args.create:
        parser.error("--batch and --create are mutually exclusive.")
    if args.no_body and not args.create:
        parser.error("--no-body only applies with --create.")
    if args.sub and (args.batch or args.create):
        parser.error("--sub is mutually exclusive with --create/--batch.")
    if args.sub and not args.category:
        parser.error("--sub requires --category.")
    if args.category and not args.sub:
        parser.error("--category only applies with --sub.")

    config = get_data_source_config(args)

    # Always resolve every Q-id first and show what was found. For read-only
    # runs that report *is* the output; for write runs it is the confirmation
    # preview (seed lookups are cached, so re-fetching during create/batch is
    # free).
    resolved = resolve_qids(args.qids)
    _print_resolution(resolved)

    if not (args.batch or args.create or args.sub):
        return 0

    resolvable = [item.qid for item in resolved if item.resolved]
    if not resolvable:
        logger.info("No Q-ids resolved; nothing to do.")
        return 0

    if args.sub:
        if not args.yes:
            confirm = input(
                f"\nFile {len(resolvable)} sub-concept(s) as {args.category!r}? [y/N]: "
            )
            if confirm.strip().lower() != "y":
                logger.info("Aborted.")
                return 0
        file_sub_concepts_from_qids(config, resolvable, args.category)
        return 0

    action = "Submit one batch to generate" if args.batch else "Create"
    body_note = " (no bodies)" if args.create and args.no_body else " (with generated bodies)"
    if not args.yes:
        confirm = input(f"\n{action} {len(resolvable)} concept(s){body_note}? [y/N]: ")
        if confirm.strip().lower() != "y":
            logger.info("Aborted.")
            return 0

    if args.batch:
        submission = submit_concept_body_batch(
            config,
            [ConceptBatchRequest(qid=qid) for qid in resolvable],
            agent_name=BATCH_AGENT_NAME,
        )
        logger.info(
            "Batch %s: queued %s, skipped %s",
            submission.batch_id,
            submission.queued,
            submission.skipped,
        )
        return 0

    create_concepts_from_qids(config, resolvable, generate_body=not args.no_body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
