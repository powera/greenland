"""
Lape lemma-facts CLI: language-independent facts stored in ``lemma_facts``.

  GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m agents.lape.lemma_facts --fact-type has_individual_instances
  PYTHONPATH=src python -m agents.lape.lemma_facts --fact-type has_individual_instances --subtype food --populate

Coverage is the default mode; --populate makes the LLM calls and saves each
result as it lands.
"""

import argparse
import logging
import sys
from typing import List

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_level_args,
    add_llm_args,
    add_pos_type_args,
    get_data_source_config,
)
from storage.config.lemma_fact_registry import LEMMA_FACT_DEFINITIONS
from storage.crud.lemma_fact import get_lemma_fact_value
from storage.models.schema import Lemma
from words.grammar_facts import GrammarFactService
from words.lemma_fact_generation import generate_lemma_fact_for_lemma
from words.lemma_selection import get_lemmas_for_agent

logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lape - language-independent lemma facts (e.g. has_individual_instances)"
    )
    add_common_args(parser)
    add_llm_args(parser)
    add_backend_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_level_args(parser)
    add_pos_type_args(parser)
    parser.add_argument(
        "--fact-type",
        required=True,
        choices=[
            fact_type
            for fact_type, definition in LEMMA_FACT_DEFINITIONS.items()
            if definition.generatable
        ],
        help="Lemma fact to generate",
    )
    parser.add_argument("--subtype", help="Only lemmas with this pos_subtype (e.g. food)")
    parser.add_argument("--limit", type=int, help="Maximum number of lemmas to process")
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Regenerate even when the fact already exists",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence score to save the fact (default: 0.7)",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Generate missing facts (default: report coverage only)",
    )
    return parser


def main() -> None:
    parser = get_argument_parser()
    args = parser.parse_args()

    config = get_data_source_config(args)
    service = GrammarFactService(config=config)
    definition = LEMMA_FACT_DEFINITIONS[args.fact_type]

    # --limit caps the LLM calls below; applying it during selection would cut
    # the pool before the subtype and missing-fact filters run.
    selection_args = argparse.Namespace(**{**vars(args), "limit": None})

    session = service.get_session()
    try:
        lemmas: List[Lemma] = [
            lemma
            for lemma in get_lemmas_for_agent(session, selection_args)
            if lemma.pos_type in definition.required_pos
            and (args.subtype is None or lemma.pos_subtype == args.subtype)
        ]
        if not lemmas:
            logger.error("No lemmas found to process")
            sys.exit(1)

        missing = [
            lemma
            for lemma in lemmas
            if get_lemma_fact_value(session, lemma.id, args.fact_type) is None
        ]
        print(f"{args.fact_type}: {len(missing)}/{len(lemmas)} missing")
        if not args.populate:
            return

        targets = lemmas if not args.skip_existing else missing
        if args.limit:
            targets = targets[: args.limit]
        if args.dry_run:
            print(f"DRY RUN - would process {len(targets)} lemmas")
            return

        client = service.get_llm_client()
        counts = {"success": 0, "failed": 0, "skipped": 0}
        for lemma in targets:
            result = generate_lemma_fact_for_lemma(
                session,
                client,
                config,
                lemma,
                args.fact_type,
                min_confidence=args.min_confidence,
                skip_existing=args.skip_existing,
            )
            if result.get("success"):
                counts["success"] += 1
                print(f"{lemma.lemma_text}: {result['fact_value']} ({result['confidence']:.2f})")
            elif result.get("skipped"):
                counts["skipped"] += 1
            else:
                counts["failed"] += 1
                print(f"{lemma.lemma_text}: FAILED {result.get('error')}")
        print(
            f"Success: {counts['success']}  Failed: {counts['failed']}  Skipped: {counts['skipped']}"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
