"""Command-line interface for the Sarka agent.

This module contains all CLI-related functionality including argument parsing,
work queue management, and the main entry point.
"""

import argparse
import logging
import sys
from typing import Any, Dict, List

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from agents.sarka.agent import (
    SarkaAgent,
    CONVERSATIONS_PER_LEVEL,
    WORDS_PER_CONVERSATION,
    WORD_USAGE_TARGET,
)
from workqueue.task_queue import TaskStatus, enqueue_task
from wordfreq.storage.models.schema import BarsukasTask

logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Sarka - Conversation Generator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show words available at level 3
  python sarka.py --level 3 --show-words

  # Generate all 12 conversations for level 3
  python sarka.py --level 3 --generate

  # Generate conversations for levels 2-5
  python sarka.py --level 2 --level-end 5 --generate

  # Dry run to see what would be generated
  python sarka.py --level 3 --generate --dry-run

  # Use workqueue for background processing
  python sarka.py --level 3 --generate --use-workqueue

  # View a generated conversation
  python sarka.py --view 123

Word definitions (compare/contrast word pairs):
  # Generate word definition narratives for level 3
  python sarka.py --level 3 --definitions

  # Dry run to preview word pairs
  python sarka.py --level 3 --definitions --dry-run

  # Generate definitions for food_drink words only
  python sarka.py --level 3 --definitions --category food_drink

  # Generate definitions with words up to level 5
  python sarka.py --level 1 --max-level 5 --definitions

Advanced options (category-based selection):
  # Generate with words up to level 5, grouped by category
  python sarka.py --level 1 --max-level 5 --by-category --generate

  # Generate for a specific category (e.g., food_drink nouns)
  python sarka.py --level 1 --max-level 5 --category food_drink --generate

  # Skip words already used in 3+ conversations
  python sarka.py --level 3 --max-word-usage 3 --generate

  # Combine options: category-coherent conversations, level cap, usage filter
  python sarka.py --level 1 --max-level 5 --by-category --max-word-usage 2 --generate

Configuration:
  - Generates {conversations} conversations per level
  - Each conversation uses {words} words from the database
  - Each word is used approximately {usage} times across all conversations

"Sarka" means "magpie" in Lithuanian - known for being talkative and social.
        """.format(
            conversations=CONVERSATIONS_PER_LEVEL,
            words=WORDS_PER_CONVERSATION,
            usage=WORD_USAGE_TARGET,
        ),
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_backend_args(parser)

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--generate",
        action="store_true",
        help="Generate conversations for the specified level(s)",
    )
    mode_group.add_argument(
        "--definitions",
        action="store_true",
        help="Generate word definition/comparison narratives for word pairs",
    )
    mode_group.add_argument(
        "--show-words",
        action="store_true",
        help="Show words available at the specified level",
    )
    mode_group.add_argument(
        "--view",
        type=int,
        metavar="ID",
        help="View a specific conversation by ID",
    )
    mode_group.add_argument(
        "--stats",
        action="store_true",
        help="Show conversation generation statistics",
    )

    # Level selection
    level_group = parser.add_argument_group("Level selection")
    level_group.add_argument(
        "--level",
        type=int,
        help="Difficulty level to generate for (required for --generate and --show-words)",
    )
    level_group.add_argument(
        "--level-end",
        type=int,
        help="End of level range (inclusive). If provided with --level, generates for all levels in range.",
    )
    level_group.add_argument(
        "--max-level",
        type=int,
        help="Maximum difficulty level (inclusive). Selects words from level 1 up to this level.",
    )

    # Generation options
    gen_group = parser.add_argument_group("Generation options")
    gen_group.add_argument(
        "--num-conversations",
        type=int,
        default=CONVERSATIONS_PER_LEVEL,
        help=f"Number of conversations per level (default: {CONVERSATIONS_PER_LEVEL})",
    )
    gen_group.add_argument(
        "--num-sentences",
        type=int,
        default=8,
        help="Target number of sentences per conversation (default: 8)",
    )
    gen_group.add_argument(
        "--max-word-usage",
        type=int,
        default=None,
        help="Skip words already used in this many conversations (default: no limit)",
    )
    gen_group.add_argument(
        "--category",
        type=str,
        default=None,
        help="Generate conversations for a specific category (pos_subtype), e.g., 'food_drink'",
    )
    gen_group.add_argument(
        "--by-category",
        action="store_true",
        help="Generate separate conversations for each noun category (keeps categories coherent)",
    )
    gen_group.add_argument(
        "--num-pairs",
        type=int,
        default=CONVERSATIONS_PER_LEVEL,
        help=f"Number of word pairs for --definitions mode (default: {CONVERSATIONS_PER_LEVEL})",
    )

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue work items for background processing by barsukas worker",
    )

    return parser


def show_level_words(agent: SarkaAgent, level: int) -> None:
    """Display words available at a specific level."""
    summary = agent.get_level_summary(level)

    print(f"\nLevel {level}: {summary['total_words']} words")
    print("-" * 40)

    for pos_type, data in sorted(summary["by_pos_type"].items()):
        print(f"  {pos_type}: {data['total']}")
        for subtype, count in sorted(data["subtypes"].items()):
            print(f"    - {subtype}: {count}")

    # Also show the actual words
    words_by_type = agent.get_words_at_level(level)
    print("\nWords:")
    for pos_type, subtypes in sorted(words_by_type.items()):
        for subtype, words in sorted(subtypes.items()):
            word_texts = [w["lemma_text"] for w in words]
            print(f"  {pos_type}/{subtype}: {', '.join(word_texts)}")


def enqueue_level_work(
    agent: SarkaAgent,
    session: Any,
    level: int,
    num_conversations: int,
    num_sentences: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Enqueue conversation generation work items for a level.

    Args:
        agent: SarkaAgent instance
        session: Database session
        level: Difficulty level to generate for
        num_conversations: Number of conversations to generate
        num_sentences: Target sentences per conversation
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    # Plan the conversations first
    conversation_plans = agent.plan_conversations_for_level(level, num_conversations)

    if not conversation_plans:
        return {
            "error": f"No words found at level {level}",
            "enqueued": 0,
            "requested": num_conversations,
        }

    enqueued_count = 0

    logger.info(
        f"Enqueuing {len(conversation_plans)} conversation generation tasks for level {level}..."
    )
    if dry_run:
        logger.info("DRY RUN MODE - No work items will be enqueued")

    for i, words in enumerate(conversation_plans):
        word_texts = [w["lemma_text"] for w in words]

        if not dry_run:
            import hashlib

            # Create a unique dedup key based on words and level
            words_str = ",".join(sorted(word_texts))
            words_hash = hashlib.md5(words_str.encode()).hexdigest()[:8]
            dedup_key = f"sarka_level{level}_{words_hash}_{i}"

            result = enqueue_task(
                session,
                task_type="sarka_generate_conversation",
                target_type="conversation",
                target_id=None,
                payload={
                    "words": [
                        {"lemma_text": w["lemma_text"], "lemma_id": w["lemma_id"]} for w in words
                    ],
                    "level": level,
                    "num_sentences": num_sentences,
                },
                dedup_key=dedup_key,
            )
            if result.created:
                enqueued_count += 1
            else:
                logger.debug(f"Skipped duplicate task {i + 1}")
        else:
            enqueued_count += 1

    if not dry_run:
        session.commit()

    return {
        "enqueued": enqueued_count,
        "requested": len(conversation_plans),
        "level": level,
        "dry_run": dry_run,
    }


def get_sarka_queue_stats(session: Any) -> Dict[str, int]:
    """Get statistics for sarka tasks in the queue."""
    task_type = "sarka_generate_conversation"
    return {
        "pending": session.query(BarsukasTask)
        .filter(BarsukasTask.task_type == task_type, BarsukasTask.status == TaskStatus.PENDING)
        .count(),
        "running": session.query(BarsukasTask)
        .filter(BarsukasTask.task_type == task_type, BarsukasTask.status == TaskStatus.RUNNING)
        .count(),
        "completed": session.query(BarsukasTask)
        .filter(BarsukasTask.task_type == task_type, BarsukasTask.status == TaskStatus.COMPLETED)
        .count(),
        "failed": session.query(BarsukasTask)
        .filter(BarsukasTask.task_type == task_type, BarsukasTask.status == TaskStatus.FAILED)
        .count(),
    }


def main() -> None:
    """Command-line interface for the Sarka agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create configuration from args
    config = get_data_source_config(args)

    # Create agent
    agent = SarkaAgent(config=config)

    # VIEW MODE: Display a specific conversation
    if args.view:
        conversation = agent.get_conversation_details(args.view)
        if not conversation:
            print(f"Conversation {args.view} not found")
            sys.exit(1)

        print("\n" + "=" * 60)
        print(f"CONVERSATION {conversation['id']}: {conversation['title']}")
        print("=" * 60)
        print(f"Level: {conversation['minimum_level']}")
        print(f"Keywords: {', '.join(conversation['keywords'])}")
        print(f"Verified: {conversation['verified']}")
        print("\n--- Sentences ---")

        for sent in conversation["sentences"]:
            en_text = sent["translations"].get("en", "(no English)")
            print(f"[{sent['speaker']}] {en_text}")

            # Show other translations if available
            for lang, text in sent["translations"].items():
                if lang != "en":
                    print(f"     ({lang}) {text}")

        print("=" * 60)
        return

    # STATS MODE: Show statistics
    if args.stats:
        session = agent.get_session()
        try:
            stats = get_sarka_queue_stats(session)
            print("\n" + "=" * 60)
            print("SARKA AGENT - QUEUE STATISTICS")
            print("=" * 60)
            print(f"Pending: {stats['pending']}")
            print(f"Running: {stats['running']}")
            print(f"Completed: {stats['completed']}")
            print(f"Failed: {stats['failed']}")
            print("=" * 60)
        finally:
            session.close()
        return

    # SHOW-WORDS MODE: Display words at a level
    if args.show_words:
        if args.level is None:
            print("Error: --level is required for --show-words")
            sys.exit(1)

        if args.level_end:
            for level in range(args.level, args.level_end + 1):
                show_level_words(agent, level)
                print()
        else:
            show_level_words(agent, args.level)
        return

    # DEFINITIONS MODE: Generate word definition/comparison narratives
    if args.definitions:
        if args.level is None:
            print("Error: --level is required for --definitions")
            sys.exit(1)

        logger.info("=" * 60)
        logger.info("SARKA AGENT - GENERATING WORD DEFINITIONS")
        logger.info("=" * 60)

        print(f"\n--- Word Definition Mode ---")
        print(f"Level: {args.level}")
        if args.max_level:
            print(f"Max level: {args.max_level}")
        if args.category:
            print(f"Category: {args.category}")
        if args.max_word_usage:
            print(f"Max word usage: {args.max_word_usage} conversations")

        result = agent.generate_definitions_for_level(
            level=args.level,
            max_level=args.max_level,
            category=args.category,
            max_word_usage=args.max_word_usage,
            num_pairs=args.num_pairs,
            num_sentences=args.num_sentences,
            dry_run=args.dry_run,
        )

        if result.get("error"):
            print(f"Error: {result['error']}")
            if result.get("plan_stats"):
                print(f"Stats: {result['plan_stats']}")
            sys.exit(1)

        # Show plan stats
        stats = result.get("plan_stats", {})
        print(f"\nWord selection:")
        print(f"  Level range: {stats.get('level_desc', 'N/A')}")
        print(f"  Total words: {stats.get('total_words', 0)}")
        if stats.get("filtered_out", 0) > 0:
            print(f"  Filtered out (usage limit): {stats['filtered_out']}")
        if stats.get("category"):
            print(f"  Category: {stats['category']}")
        print(f"  Planned pairs: {stats.get('planned_pairs', 0)}")

        print(f"\nGenerated: {result['successful']}/{result['total']} definitions")
        if result["failed"] > 0:
            print(f"Failed: {result['failed']}")

        # Show results
        if result.get("results"):
            print("\nWord definitions:")
            for i, res in enumerate(result["results"][:5], 1):
                if res.get("success") or res.get("dry_run"):
                    words_str = " / ".join(res.get("words", []))
                    print(
                        f"  {i}. {words_str}: {res.get('title')} ({res.get('num_sentences')} sentences)"
                    )
                    if res.get("dry_run") and res.get("sentences"):
                        for sent in res["sentences"]:
                            text = sent.get("text", sent) if isinstance(sent, dict) else sent
                            print(f"     {text}")
                else:
                    print(f"  {i}. Error: {res.get('error')}")

        print("\n" + "=" * 60)
        print("DEFINITION GENERATION SUMMARY")
        print("=" * 60)
        print(f"Total successful: {result['successful']}")
        print(f"Total failed: {result['failed']}")
        if args.dry_run:
            print("\n[DRY RUN] No definitions were actually saved")
        print("=" * 60)
        return

    # GENERATE MODE
    if args.generate:
        if args.level is None:
            print("Error: --level is required for --generate")
            sys.exit(1)

        levels = [args.level]
        if args.level_end:
            levels = list(range(args.level, args.level_end + 1))

        # WORKQUEUE MODE: Enqueue work for background processing
        if args.use_workqueue:
            logger.info("=" * 60)
            logger.info("SARKA AGENT - ENQUEUING WORK")
            logger.info("=" * 60)

            session = agent.get_session()
            try:
                total_enqueued = 0
                for level in levels:
                    results = enqueue_level_work(
                        agent=agent,
                        session=session,
                        level=level,
                        num_conversations=args.num_conversations,
                        num_sentences=args.num_sentences,
                        dry_run=args.dry_run,
                    )

                    print(f"\nLevel {level}:")
                    print(f"  Requested: {results['requested']}")
                    print(f"  Enqueued: {results['enqueued']}")
                    if results.get("error"):
                        print(f"  Error: {results['error']}")

                    total_enqueued += results["enqueued"]

                print("\n" + "=" * 60)
                print("WORK ENQUEUE SUMMARY")
                print("=" * 60)
                print(f"Levels: {levels}")
                print(f"Total enqueued: {total_enqueued}")
                if args.dry_run:
                    print("\n[DRY RUN] No work items were actually enqueued")
                print("=" * 60)

                # Show queue stats
                if not args.dry_run:
                    stats = get_sarka_queue_stats(session)
                    print("\nCurrent queue status:")
                    print(f"  Pending: {stats['pending']}")
                    print(f"  Running: {stats['running']}")
                    print(f"  Completed: {stats['completed']}")
                    print(f"  Failed: {stats['failed']}")
                    print("=" * 60)

            except Exception as e:
                logger.error(f"Failed to enqueue work: {e}")
                sys.exit(1)
            finally:
                session.close()
            return

        # IMMEDIATE MODE: Generate directly
        logger.info("=" * 60)
        logger.info("SARKA AGENT - GENERATING CONVERSATIONS")
        logger.info("=" * 60)

        # Check if using new options (max_level, category, by_category, max_word_usage)
        use_new_options = (
            args.max_level is not None
            or args.category is not None
            or args.by_category
            or args.max_word_usage is not None
        )

        if use_new_options:
            # Use new generate_with_options method
            print(f"\n--- Using advanced options ---")
            if args.max_level:
                print(f"Max level: {args.max_level}")
            if args.category:
                print(f"Category: {args.category}")
            if args.by_category:
                print("Grouping by category for coherent conversations")
            if args.max_word_usage:
                print(f"Max word usage: {args.max_word_usage} conversations")

            result = agent.generate_with_options(
                max_level=args.max_level,
                level=args.level,
                category=args.category,
                by_category=args.by_category,
                max_word_usage=args.max_word_usage,
                num_conversations=args.num_conversations,
                num_sentences=args.num_sentences,
                dry_run=args.dry_run,
            )

            if result.get("error"):
                print(f"Error: {result['error']}")
                if result.get("plan_stats"):
                    print(f"Stats: {result['plan_stats']}")
                sys.exit(1)

            # Show plan stats
            stats = result.get("plan_stats", {})
            print(f"\nWord selection:")
            print(f"  Level range: {stats.get('level_desc', 'N/A')}")
            print(f"  Total words: {stats.get('total_words', 0)}")
            if stats.get("filtered_out", 0) > 0:
                print(f"  Filtered out (usage limit): {stats['filtered_out']}")
            if stats.get("category"):
                print(f"  Category: {stats['category']}")
            print(f"  By category grouping: {stats.get('by_category', False)}")

            print(f"\nGenerated: {result['successful']}/{result['total']} conversations")
            if result["failed"] > 0:
                print(f"Failed: {result['failed']}")

            # Show sample results
            if result.get("results"):
                print("\nSample conversations:")
                for i, res in enumerate(result["results"][:5], 1):
                    if res.get("success") or res.get("dry_run"):
                        words_str = ", ".join(res.get("words", []))
                        print(f"  {i}. {res.get('title')} ({res.get('num_sentences')} sentences)")
                        print(f"     Words: {words_str}")
                    else:
                        print(f"  {i}. Error: {res.get('error')}")

            print("\n" + "=" * 60)
            print("GENERATION SUMMARY")
            print("=" * 60)
            print(f"Total successful: {result['successful']}")
            print(f"Total failed: {result['failed']}")
            if args.dry_run:
                print("\n[DRY RUN] No conversations were actually saved")
            print("=" * 60)

        else:
            # Use original per-level generation
            all_results = []
            total_successful = 0
            total_failed = 0

            for level in levels:
                print(f"\n--- Level {level} ---")

                result = agent.generate_for_level(
                    level=level,
                    num_conversations=args.num_conversations,
                    num_sentences=args.num_sentences,
                    dry_run=args.dry_run,
                )

                if result.get("error"):
                    print(f"Error: {result['error']}")
                    continue

                all_results.append(result)
                total_successful += result["successful"]
                total_failed += result["failed"]

                # Show level summary
                summary = result["level_summary"]
                print(f"Words at level: {summary['total_words']}")
                for pos_type, data in summary["by_pos_type"].items():
                    subtypes_str = ", ".join(f"{k}: {v}" for k, v in data["subtypes"].items())
                    print(f"  {pos_type}: {data['total']} ({subtypes_str})")

                print(f"\nGenerated: {result['successful']}/{result['total']} conversations")
                if result["failed"] > 0:
                    print(f"Failed: {result['failed']}")

                # Show sample results
                if result["results"]:
                    print("\nSample conversations:")
                    for i, res in enumerate(result["results"][:3], 1):
                        if res.get("success") or res.get("dry_run"):
                            words_str = ", ".join(res.get("words", []))
                            print(
                                f"  {i}. {res.get('title')} ({res.get('num_sentences')} sentences)"
                            )
                            print(f"     Words: {words_str}")
                        else:
                            print(f"  {i}. Error: {res.get('error')}")

            print("\n" + "=" * 60)
            print("GENERATION SUMMARY")
            print("=" * 60)
            print(f"Levels: {levels}")
            print(f"Total successful: {total_successful}")
            print(f"Total failed: {total_failed}")
            if args.dry_run:
                print("\n[DRY RUN] No conversations were actually saved")
            print("=" * 60)


if __name__ == "__main__":
    main()
