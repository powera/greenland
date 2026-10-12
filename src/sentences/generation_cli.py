#!/usr/bin/env python3
"""Command-line interface for sentence generation.

Generates general LLM or vocabulary-guided examples. Mechanical practice
sentences live in langtools.sentence_patterns and never use this CLI.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sentences.generation import SentenceGenerationService
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_llm_args,
    get_data_source_config,
)
from words.lemma_selection import get_lemmas_for_agent
from storage.models.schema import Lemma
from workqueue.task_queue import TaskType, enqueue_task

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
  # Generate LLM sentences for a GUID
  python -m agents.buivolas --task generate-sentences --mode llm --guid N06_001 --num-sentences 3 --language lt zh fr es en

  # Generate guided sentences (vocabulary-aware) for a GUID
  python -m agents.buivolas --task generate-sentences --mode guided --guid N06_001 --num-sentences 5

  # Generate guided sentences for all lemmas at a difficulty level
  python -m agents.buivolas --task generate-sentences --mode guided --level 3 --num-sentences 5 --limit 10
        """,
    )

    add_common_args(parser)
    add_llm_args(parser)
    add_guid_arg(parser, help_text="Target this lemma GUID")
    add_backend_args(parser)

    # Task selection
    parser.add_argument(
        "--task",
        choices=["generate-sentences"],
        required=True,
        help="Task to execute",
    )

    # Arguments for generate-sentences task
    parser.add_argument(
        "--mode",
        choices=["llm", "guided"],
        help="Sentence generation mode: llm (basic), guided (vocabulary-aware)",
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
        help="Generate LLM sentences for lemmas at a specific difficulty level (1-199, for llm mode)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of lemmas to process (for llm mode)",
    )
    parser.add_argument(
        "--language",
        nargs="+",
        help="Target languages for translations (e.g., lt zh fr es en)",
    )
    parser.add_argument(
        "--execute-inline",
        action="store_true",
        help="Execute immediately instead of enqueueing work (debugging only)",
    )

    return parser


def _get_llm_lemmas(service: SentenceGenerationService, args: argparse.Namespace) -> list[Lemma]:
    """Get lemmas for LLM sentence generation.

    Supports nouns, verbs, and adjectives. Other POS types will be filtered out.
    """
    session = service.get_session()
    try:
        if args.level:
            from words.lemma_selection import LemmaQueryBuilder, apply_limit_and_sample_rate

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


def enqueue_generation_work(service: SentenceGenerationService, args: argparse.Namespace) -> int:
    """Discover sentence-generation work and enqueue capability-named tasks."""
    session = service.get_session()
    try:
        lemmas = _get_llm_lemmas(service, args)
        if not lemmas:
            logger.error("No supported lemmas found for sentence generation")
            return 1

        enqueued_count = 0
        for lemma in lemmas:
            if args.dry_run:
                logger.info("Would queue %s sentence generation for %s", args.mode, lemma.guid)
                enqueued_count += 1
                continue
            result = enqueue_task(
                session,
                task_type=TaskType.SENTENCES_EXAMPLES_GENERATE,
                target_type="lemma",
                target_id=lemma.id,
                payload={
                    "schema_version": 1,
                    "lemma_id": lemma.id,
                    "mode": args.mode,
                    "num_sentences": args.num_sentences,
                    "difficulty_context": args.level,
                    "max_vocabulary_level": 7,
                    "model": service.config.model,
                    "source_component": "agents.buivolas",
                },
                dedup_key=f"{TaskType.SENTENCES_EXAMPLES_GENERATE}:{lemma.id}:{args.mode}",
            )
            if result.created:
                enqueued_count += 1
        session.commit()
        logger.info("Queued %s sentence-generation task(s)", enqueued_count)
        return 0
    finally:
        session.close()


def main() -> int:
    parser = get_argument_parser()
    args = parser.parse_args()

    if not args.mode:
        parser.error("generate-sentences requires --mode (llm or guided)")

    config = get_data_source_config(args)
    service = SentenceGenerationService(config=config, dry_run=args.dry_run)

    if not args.execute_inline:
        return enqueue_generation_work(service, args)

    if args.task == "generate-sentences":
        if args.mode == "guided":
            # Guided mode: vocabulary-aware sentence generation
            lemmas = _get_llm_lemmas(service, args)

            if not lemmas:
                if args.guid:
                    session = service.get_session()
                    try:
                        all_lemmas = get_lemmas_for_agent(session, args)
                        if all_lemmas:
                            unsupported = all_lemmas[0]
                            logger.info(
                                "Lemma %s has POS type '%s' - sentence generation only supports nouns, verbs, and adjectives. Skipping.",
                                args.guid,
                                unsupported.pos_type,
                            )
                            return 0
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
                logger.info("Processing (guided): %s (GUID: %s)", lemma.lemma_text, lemma.guid)
            else:
                logger.info("Processing %s lemmas (guided mode)", len(lemmas))
                if args.level:
                    logger.info("Difficulty level: %s", args.level)

            total_generated = 0
            total_stored = 0
            total_skipped = 0
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

                result = service.generate_guided_sentences_for_lemma(
                    lemma=lemma,
                    num_sentences=args.num_sentences,
                    max_vocabulary_level=7,
                )

                if result.get("skipped"):
                    logger.info("Skipped %s: %s", lemma.lemma_text, result.get("reason"))
                    total_skipped += 1
                    continue

                if result.get("success") and result.get("sentences"):
                    sentences = result["sentences"]
                    total_generated += len(sentences)

                    # Log the generated sentences
                    for sent in sentences:
                        en_text = sent.get("en", "")
                        words_used = sent.get("words_used", [])
                        lemmas_str = ", ".join(w.get("lemma", "") for w in words_used)
                        logger.info("  -> %s", en_text)
                        logger.info("     words: %s", lemmas_str)

                    if not args.dry_run:
                        session = service.get_session()
                        try:
                            store_result = service.store_guided_sentences(
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

        else:  # llm mode
            lemmas = _get_llm_lemmas(service, args)

            if not lemmas:
                if args.guid:
                    # Check if the lemma exists but is unsupported POS type
                    session = service.get_session()
                    try:
                        from words.lemma_selection import get_lemmas_for_agent

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

                result = service.generate_llm_sentences_for_lemma(
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
                        session = service.get_session()
                        try:
                            store_result = service.store_llm_sentences(
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
