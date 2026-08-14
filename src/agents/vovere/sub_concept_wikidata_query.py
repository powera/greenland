#!/usr/bin/env python3
"""Populate one sub-concept category from a simple Wikidata SPARQL query.

This is intentionally a starter tool: it supports a few common "what is this
Q-id?" patterns (instance-of/subclass trees, optional country constraint, and
minimum sitelink counts), then files the resulting Q-ids through the same
sub-concept service used by Barsukas and Voveraite.

Query construction and execution live in
:mod:`concepts.seed.wikidata_query`; filing lives in
:mod:`concepts.seed.qids`. This module is the command line only.

Examples:
    PYTHONPATH=src python src/agents/vovere/sub_concept_wikidata_query.py \
        --category geography_river --class-qid Q4022 --yes
    PYTHONPATH=src python src/agents/vovere/sub_concept_wikidata_query.py \
        --category media_tv_episode --preset media_tv_episode --limit 500 --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src directory to path (this file lives at src/agents/vovere/)
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from concepts.seed.qids import file_sub_concepts_from_qids
from concepts.seed.wikidata_query import PRESET_CLASS_QIDS, build_class_query, query_class_qids
from storage.models.concept import ALL_SUB_CONCEPT_CATEGORIES

logger = logging.getLogger(__name__)

# Number of matched Q-ids listed before the preview is truncated.
PREVIEW_LIMIT: int = 20


def _load_sparql_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Populate a sub-concept category from a Wikidata SPARQL query."
    )
    parser.add_argument("--category", required=True, choices=ALL_SUB_CONCEPT_CATEGORIES)
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_CLASS_QIDS),
        help="Use a built-in class Q-id for a known sub-concept category.",
    )
    parser.add_argument(
        "--class-qid",
        help="Wikidata class Q-id to query (overrides the preset's class Q-id).",
    )
    parser.add_argument(
        "--pattern",
        choices=("direct-instance", "instance-tree", "subclass-tree"),
        default="instance-tree",
        help="Common SPARQL pattern to use with --class-qid/--preset.",
    )
    parser.add_argument(
        "--country-qid",
        help="Optional country Q-id constraint via wdt:P17 (e.g. Q183 for Germany).",
    )
    parser.add_argument("--min-sitelinks", type=int, default=250)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--sparql-file", help="Use a bespoke SPARQL file instead of a class query.")
    add_common_args(parser)
    add_backend_args(parser)
    return parser


def main() -> int:
    parser = get_argument_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
    )

    class_qid = args.class_qid or (PRESET_CLASS_QIDS.get(args.preset) if args.preset else None)
    if args.sparql_file:
        sparql = _load_sparql_file(args.sparql_file)
    elif class_qid:
        sparql = build_class_query(
            class_qid=class_qid,
            pattern=args.pattern,
            country_qid=args.country_qid,
            min_sitelinks=args.min_sitelinks,
            limit=args.limit,
        )
    else:
        parser.error("Provide --preset, --class-qid, or --sparql-file.")

    config = get_data_source_config(args)
    logger.info("Querying Wikidata for %s", args.category)
    qids = query_class_qids(sparql)
    logger.info("Found %d Q-id(s)", len(qids))
    for qid in qids[:PREVIEW_LIMIT]:
        logger.info("MATCH %s", qid)
    if len(qids) > PREVIEW_LIMIT:
        logger.info("...and %d more", len(qids) - PREVIEW_LIMIT)

    if args.dry_run:
        logger.info("Dry run; not filing sub-concepts.")
        return 0

    if not args.yes:
        confirm = input(f"\nFile {len(qids)} Q-id(s) as {args.category!r}? [y/N]: ")
        if confirm.strip().lower() != "y":
            logger.info("Aborted.")
            return 0

    file_sub_concepts_from_qids(config, qids, args.category)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
