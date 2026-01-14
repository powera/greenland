#!/usr/bin/env python3
"""
Buivolas - Sentence Creation Agent

This agent generates example sentences for vocabulary words, using either:
- Pattern templates (mechanical generation), or
- LLM-driven sentence generation with word-level annotations.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.buivolas.agent import BuivolasAgent
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_llm_args,
    get_data_source_config,
)
from agents.common.lemma_selection import get_lemmas_for_agent
from wordfreq.patterns.simple_patterns import SIMPLE_PATTERNS
from wordfreq.storage.models.schema import Lemma

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Buivolas - Sentence Creation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate candidate sentences for specific patterns
  python -m agents.buivolas --task generate-candidates --patterns where_is_noun my_noun_is_color --limit 100

  # Generate candidates for all patterns
  python -m agents.buivolas --task generate-candidates --all-patterns --limit 1000

  # Generate pattern sentences for a GUID
  python -m agents.buivolas --task generate-sentences --mode pattern --guid N06_001 --pattern-limit 10

  # Generate LLM sentences for a GUID
  python -m agents.buivolas --task generate-sentences --mode llm --guid N06_001 --num-sentences 3 --language lt zh fr es en
        """,
    )

    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_guid_arg(parser, help_text="Target this lemma GUID")
    add_backend_args(parser)

    # Task selection
    parser.add_argument(
        "--task",
        choices=["generate-candidates", "generate-sentences"],
        required=True,
        help="Task to execute",
    )

    # Arguments for generate-candidates task
    parser.add_argument(
        "--patterns", nargs="+", help="Specific pattern IDs to generate (for generate-candidates)"
    )
    parser.add_argument(
        "--all-patterns",
        action="store_true",
        help="Generate for all patterns (for generate-candidates)",
    )

    # Arguments for generate-sentences task
    parser.add_argument(
        "--mode",
        choices=["pattern", "llm"],
        help="Sentence generation mode (for generate-sentences)",
    )
    parser.add_argument(
        "--pattern-limit",
        type=int,
        help="Max combinations per compatible pattern (for pattern mode)",
    )
    parser.add_argument(
        "--num-sentences",
        type=int,
        default=3,
        help="Number of LLM sentences to generate per lemma (for llm mode)",
    )
    parser.add_argument(
        "--level",
        type=int,
        help="Generate LLM sentences for lemmas at a specific difficulty level (1-20, for llm mode)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of lemmas to process (for llm mode) or max combinations per pattern (for generate-candidates)",
    )
    parser.add_argument(
        "--language",
        nargs="+",
        help="Target languages for translations (e.g., lt zh fr es en)",
    )

    return parser


def _get_llm_lemmas(agent: BuivolasAgent, args: argparse.Namespace) -> list[Lemma]:
    """Get lemmas for LLM sentence generation.

    Supports nouns, verbs, and adjectives. Other POS types will be filtered out.
    """
    session = agent.get_session()
    try:
        if args.level:
            from agents.common.lemma_selection import LemmaQueryBuilder, apply_limit_and_sample_rate

            query = (
                LemmaQueryBuilder(session)
                .curated_only()
                .by_difficulty_level(args.level)
                .filter_custom(
                    lambda q: q.filter(Lemma.pos_type.in_(["noun", "verb", "adjective"]))
                )
                .order_by_id()
                .build()
            )
            lemmas = apply_limit_and_sample_rate(
                query, args.limit, getattr(args, "sample_rate", 1.0)
            )
        else:
            lemmas = get_lemmas_for_agent(session, args)
            # Support nouns, verbs, and adjectives
            lemmas = [lemma for lemma in lemmas if lemma.pos_type in ("noun", "verb", "adjective")]
    finally:
        session.close()

    return lemmas


def main() -> int:
    parser = get_argument_parser()
    args = parser.parse_args()

    # Validate arguments based on task
    if args.task == "generate-candidates":
        if not args.patterns and not args.all_patterns:
            parser.error("generate-candidates requires either --patterns or --all-patterns")
    elif args.task == "generate-sentences":
        if not args.mode:
            parser.error("generate-sentences requires --mode (pattern or llm)")

    config = get_data_source_config(args)
    agent = BuivolasAgent(config=config, dry_run=args.dry_run)

    if args.task == "generate-candidates":
        pattern_dict = {p["pattern_id"]: p for p in SIMPLE_PATTERNS}

        if args.all_patterns:
            results = agent.pattern_generator.generate_candidates_all_patterns(
                max_per_pattern=args.limit
            )

            logger.info("=" * 80)
            logger.info("BUIVOLAS - CANDIDATE GENERATION REPORT")
            logger.info("=" * 80)
            logger.info("Patterns processed: %s", results["patterns_processed"])
            logger.info("Total candidates: %s", results["total_candidates"])
            logger.info("Successful: %s", results["total_success"])
            logger.info("Duplicates: %s", results["total_duplicates"])
            logger.info("Errors: %s", results["total_errors"])
            if args.dry_run:
                logger.info("DRY RUN - No database changes made")
            logger.info("=" * 80)

        else:
            patterns_to_generate = []
            for pattern_id in args.patterns:
                if pattern_id in pattern_dict:
                    patterns_to_generate.append(pattern_dict[pattern_id])
                else:
                    logger.error("Unknown pattern: %s", pattern_id)
                    available = ", ".join(sorted(pattern_dict.keys()))  # type: ignore[arg-type]
                    logger.error("Available patterns: %s", available)
                    return 1

            total_success = 0
            total_duplicates = 0
            total_errors = 0
            total_candidates = 0

            for pattern in patterns_to_generate:
                result = agent.pattern_generator.generate_candidates_for_pattern(
                    pattern, max_combinations=args.limit
                )
                total_candidates += result.get("total", 0)
                total_success += result.get("success_count", 0)
                total_duplicates += result.get("duplicate_count", 0)
                total_errors += result.get("error_count", 0)

            logger.info("=" * 80)
            logger.info("BUIVOLAS - CANDIDATE GENERATION REPORT")
            logger.info("=" * 80)
            logger.info("Patterns: %s", ", ".join(args.patterns))
            logger.info("Total candidates: %s", total_candidates)
            logger.info("Successful: %s", total_success)
            logger.info("Duplicates: %s", total_duplicates)
            logger.info("Errors: %s", total_errors)
            if args.dry_run:
                logger.info("DRY RUN - No database changes made")
            logger.info("=" * 80)

    elif args.task == "generate-sentences":
        if args.mode == "pattern":
            if not args.guid:
                logger.error("--guid is required for pattern sentence generation")
                return 1

            result = agent.generate_pattern_sentences_for_guid(
                guid=args.guid, max_combinations=args.pattern_limit
            )

            logger.info("=" * 80)
            logger.info("BUIVOLAS - PATTERN GUID GENERATION REPORT")
            logger.info("=" * 80)
            if result.get("success"):
                logger.info("Patterns processed: %s", result.get("processed", 0))
                logger.info("Sentences stored: %s", result.get("stored", 0))
                logger.info("Duplicates: %s", result.get("duplicates", 0))
                logger.info("Errors: %s", result.get("errors", 0))
            else:
                logger.error(result.get("error", "Unknown error generating patterns"))
            if args.dry_run:
                logger.info("DRY RUN - No database changes made")
            logger.info("=" * 80)

        else:
            lemmas = _get_llm_lemmas(agent, args)

            if not lemmas:
                if args.guid:
                    # Check if the lemma exists but is unsupported POS type
                    session = agent.get_session()
                    try:
                        from agents.common.lemma_selection import get_lemmas_for_agent

                        all_lemmas = get_lemmas_for_agent(session, args)
                        if all_lemmas:
                            unsupported = all_lemmas[0]
                            logger.info(
                                "Lemma %s has POS type '%s' - sentence generation only supports nouns, verbs, and adjectives. Skipping.",
                                args.guid,
                                unsupported.pos_type,
                            )
                            return 0  # Exit gracefully, not an error
                        else:
                            logger.error("Lemma %s does not exist", args.guid)
                            return 1
                    finally:
                        session.close()
                elif args.level:
                    logger.error(
                        "No nouns, verbs, or adjectives found at difficulty level %s", args.level
                    )
                else:
                    logger.error("No lemmas to process. Specify --guid or --level")
                    parser.print_help()
                return 1

            if len(lemmas) == 1:
                lemma = lemmas[0]
                logger.info("Processing: %s (GUID: %s)", lemma.lemma_text, lemma.guid)
            else:
                logger.info("Processing %s lemmas (nouns, verbs, adjectives)", len(lemmas))
                if args.level:
                    logger.info("Difficulty level: %s", args.level)

            total_generated = 0
            total_stored = 0
            total_failed = 0
            total_skipped = 0

            for i, lemma in enumerate(lemmas, 1):
                if len(lemmas) > 1:
                    logger.info(
                        "\n[%s/%s] Processing: %s (%s)",
                        i,
                        len(lemmas),
                        lemma.lemma_text,
                        lemma.guid,
                    )

                result = agent.generate_llm_sentences_for_lemma(
                    lemma=lemma,
                    num_sentences=args.num_sentences,
                    difficulty_context=args.level if args.level else None,
                )

                if result.get("skipped"):
                    logger.info("Skipped %s: %s", lemma.lemma_text, result.get("reason"))
                    total_skipped += 1
                    continue

                if result.get("success") and result.get("sentences"):
                    sentences = result["sentences"]
                    total_generated += len(sentences)

                    if not args.dry_run:
                        session = agent.get_session()
                        try:
                            store_result = agent.store_llm_sentences(
                                sentences_data=sentences,
                                source_lemma=lemma,
                                session=session,
                            )
                            total_stored += store_result["stored"]
                            total_failed += store_result["failed"]

                            logger.info(
                                "Stored: %s, Failed: %s",
                                store_result["stored"],
                                store_result["failed"],
                            )
                        finally:
                            session.close()
                    else:
                        logger.info("Would store %s sentences (dry run)", len(sentences))
                else:
                    logger.error(
                        "Generation failed for %s: %s",
                        lemma.lemma_text,
                        result.get("error"),
                    )
                    total_failed += 1

            if len(lemmas) > 1:
                logger.info("\n%s", "=" * 60)
                logger.info("Generation complete!")
                logger.info("Lemmas processed: %s", len(lemmas))
                if total_skipped > 0:
                    logger.info("Lemmas skipped: %s", total_skipped)
                logger.info("Sentences generated: %s", total_generated)
                if not args.dry_run:
                    logger.info("Sentences stored: %s", total_stored)
                    logger.info("Sentences failed: %s", total_failed)
                logger.info("%s", "=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
