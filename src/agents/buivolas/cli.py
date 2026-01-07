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
    add_language_args,
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


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Buivolas - Sentence Creation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate candidate sentences for specific patterns
  python -m agents.buivolas.cli generate-candidates --patterns where_is_noun my_noun_is_color --limit 100

  # Generate candidates for all patterns
  python -m agents.buivolas.cli generate-candidates --all-patterns --limit 1000

  # Generate pattern sentences for a GUID
  python -m agents.buivolas.cli generate-sentences --mode pattern --guid N06_001 --pattern-limit 10

  # Generate LLM sentences for a GUID
  python -m agents.buivolas.cli generate-sentences --mode llm --guid N06_001 --num-sentences 3
        """,
    )

    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_guid_arg(parser, help_text="Target this lemma GUID")
    add_backend_args(parser)

    subparsers = parser.add_subparsers(dest="command", help="Command to execute", required=True)

    gen_parser = subparsers.add_parser(
        "generate-candidates",
        help="Generate candidate pattern sentences without translations",
    )
    gen_group = gen_parser.add_mutually_exclusive_group(required=True)
    gen_group.add_argument("--patterns", nargs="+", help="Specific pattern IDs to generate")
    gen_group.add_argument("--all-patterns", action="store_true", help="Generate for all patterns")
    gen_parser.add_argument("--limit", type=int, help="Max combinations per pattern")

    sentence_parser = subparsers.add_parser(
        "generate-sentences",
        help="Generate sentences for a GUID using pattern or LLM mode",
    )
    sentence_parser.add_argument(
        "--mode",
        choices=["pattern", "llm"],
        required=True,
        help="Sentence generation mode",
    )
    sentence_parser.add_argument(
        "--pattern-limit",
        type=int,
        help="Max combinations per compatible pattern (pattern mode)",
    )
    sentence_parser.add_argument(
        "--num-sentences",
        type=int,
        default=3,
        help="Number of LLM sentences to generate per noun (llm mode)",
    )
    sentence_parser.add_argument(
        "--level",
        type=int,
        help="Generate LLM sentences for nouns at a specific difficulty level (1-20)",
    )
    sentence_parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of lemmas to process (llm mode)",
    )
    add_language_args(sentence_parser, multiple=True)

    submit_parser = subparsers.add_parser(
        "submit-batch",
        help="Submit batch translation job for untranslated sentences",
    )
    submit_parser.add_argument(
        "--languages",
        nargs="+",
        required=True,
        choices=["lt", "zh", "ko", "fr", "de", "es", "pt"],
        help="Target languages to translate to",
    )
    submit_parser.add_argument("--limit", type=int, help="Max sentences to translate")
    submit_parser.add_argument("--pattern-id", help="Only translate sentences from this pattern")

    check_parser = subparsers.add_parser(
        "check-batch",
        help="Check status of a batch translation job",
    )
    check_parser.add_argument("--batch-id", required=True, help="Batch ID to check")

    retrieve_parser = subparsers.add_parser(
        "retrieve-batch",
        help="Retrieve and apply batch translation results",
    )
    retrieve_parser.add_argument("--batch-id", required=True, help="Batch ID to retrieve")

    subparsers.add_parser("list-batches", help="List active batch translation jobs")

    parser.set_defaults(languages=["en", "lt", "zh", "ko", "fr", "es", "de", "pt", "sw", "vi"])

    return parser


def _get_llm_lemmas(agent: BuivolasAgent, args) -> list[Lemma]:
    session = agent.get_session()
    try:
        if args.level:
            from agents.common.lemma_selection import LemmaQueryBuilder, apply_limit_and_sample_rate

            query = (
                LemmaQueryBuilder(session)
                .curated_only()
                .by_difficulty_level(args.level)
                .filter_custom(lambda q: q.filter(Lemma.pos_type == "noun"))
                .order_by_id()
                .build()
            )
            lemmas = apply_limit_and_sample_rate(
                query, args.limit, getattr(args, "sample_rate", 1.0)
            )
        else:
            lemmas = get_lemmas_for_agent(session, args)
            lemmas = [lemma for lemma in lemmas if lemma.pos_type == "noun"]
    finally:
        session.close()

    return lemmas


def main() -> int:
    parser = get_argument_parser()
    args = parser.parse_args()

    config = get_data_source_config(args)
    agent = BuivolasAgent(config=config, dry_run=args.dry_run)

    if args.command == "generate-candidates":
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
                    available = ", ".join(pattern_dict.keys())
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

    elif args.command == "generate-sentences":
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
                    logger.error("Lemma %s is not a noun or does not exist", args.guid)
                elif args.level:
                    logger.error("No nouns found at difficulty level %s", args.level)
                else:
                    logger.error("No lemmas to process. Specify --guid or --level")
                    parser.print_help()
                return 1

            if len(lemmas) == 1:
                lemma = lemmas[0]
                logger.info("Processing: %s (GUID: %s)", lemma.lemma_text, lemma.guid)
            else:
                logger.info("Processing %s nouns", len(lemmas))
                if args.level:
                    logger.info("Difficulty level: %s", args.level)

            total_generated = 0
            total_stored = 0
            total_failed = 0

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
                    target_languages=args.languages,
                    num_sentences=args.num_sentences,
                    difficulty_context=args.level if args.level else None,
                )

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
                logger.info("Nouns processed: %s", len(lemmas))
                logger.info("Sentences generated: %s", total_generated)
                if not args.dry_run:
                    logger.info("Sentences stored: %s", total_stored)
                    logger.info("Sentences failed: %s", total_failed)
                logger.info("%s", "=" * 60)

    elif args.command == "submit-batch":
        batch_id, count = agent.pattern_generator.submit_batch_translation(
            target_languages=args.languages,
            limit=args.limit,
            pattern_id=args.pattern_id,
        )

        if batch_id:
            logger.info("=" * 80)
            logger.info("BUIVOLAS - BATCH SUBMISSION REPORT")
            logger.info("=" * 80)
            logger.info("Batch ID: %s", batch_id)
            logger.info("Requests submitted: %s", count)
            logger.info("Target languages: %s", ", ".join(args.languages))
            logger.info("=" * 80)
            logger.info(
                "Check status with: python -m agents.buivolas.cli check-batch --batch-id %s",
                batch_id,
            )
        else:
            logger.warning("No batch submitted (no untranslated sentences found)")

    elif args.command == "check-batch":
        batch_info = agent.pattern_generator.check_batch_status(args.batch_id)

        logger.info("=" * 80)
        logger.info("BUIVOLAS - BATCH STATUS")
        logger.info("=" * 80)
        logger.info("Batch ID: %s", batch_info["id"])
        logger.info("Status: %s", batch_info["status"])
        logger.info("Created at: %s", batch_info.get("created_at"))

        counts = batch_info.get("request_counts", {})
        logger.info("Total requests: %s", counts.get("total", 0))
        logger.info("Completed: %s", counts.get("completed", 0))
        logger.info("Failed: %s", counts.get("failed", 0))
        logger.info("=" * 80)

        if batch_info["status"] == "completed":
            logger.info(
                "Retrieve results with: python -m agents.buivolas.cli retrieve-batch --batch-id %s",
                args.batch_id,
            )

    elif args.command == "retrieve-batch":
        count = agent.pattern_generator.retrieve_batch_results(args.batch_id)

        logger.info("=" * 80)
        logger.info("BUIVOLAS - BATCH RESULTS APPLIED")
        logger.info("=" * 80)
        logger.info("Batch ID: %s", args.batch_id)
        logger.info("Sentences updated: %s", count)
        logger.info("=" * 80)

    elif args.command == "list-batches":
        active_batches = agent.pattern_generator.batch_manager.list_active_batches()

        logger.info("=" * 80)
        logger.info("BUIVOLAS - ACTIVE BATCHES")
        logger.info("=" * 80)

        if active_batches:
            for batch_id in active_batches:
                try:
                    batch_info = agent.pattern_generator.check_batch_status(batch_id)
                    openai_status = batch_info.get("status", "unknown")
                    logger.info("\nBatch: %s", batch_id)
                    logger.info("  OpenAI Status: %s", openai_status)

                    if "request_counts" in batch_info:
                        counts = batch_info["request_counts"]
                        logger.info(
                            "  Total: %s, Completed: %s, Failed: %s",
                            counts.get("total", 0),
                            counts.get("completed", 0),
                            counts.get("failed", 0),
                        )

                    summary = agent.pattern_generator.batch_manager.get_batch_summary(batch_id)
                    logger.info("  Local DB status counts: %s", summary["status_counts"])
                except Exception as e:
                    logger.warning("  Failed to check status for %s: %s", batch_id, e)
                    summary = agent.pattern_generator.batch_manager.get_batch_summary(batch_id)
                    logger.info("\nBatch: %s", batch_id)
                    logger.info("  Total requests: %s", summary["total_requests"])
                    logger.info("  Status counts: %s", summary["status_counts"])
        else:
            logger.info("No active batches")

        logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
