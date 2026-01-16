"""Command-line interface for the Sarka agent.

This module contains all CLI-related functionality including argument parsing,
work queue management, and the main entry point.
"""

import argparse
import logging
import sys
from typing import Dict, List

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from agents.sarka.agent import SarkaAgent, KEYWORD_CATEGORIES, CONVERSATION_THEMES
from barsukas.utils.task_queue import TaskStatus, enqueue_task
from wordfreq.storage.models.schema import BarsukasTask

logger = logging.getLogger(__name__)


def get_argument_parser():
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Sarka - Conversation Generator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate a single conversation with random keywords
  python sarka.py --generate

  # Generate 10 conversations
  python sarka.py --generate --count 10

  # Generate with specific keywords
  python sarka.py --generate --colors red blue --body-part hand --emotion happy --occupation doctor

  # Dry run to see what would be generated
  python sarka.py --generate --dry-run

  # Use workqueue for background processing
  python sarka.py --generate --count 20 --use-workqueue

  # View a generated conversation
  python sarka.py --view 123

Available keyword categories:
  Colors: red, blue, green, yellow, orange, purple, pink, brown, black, white, gray, gold
  Body parts: head, hand, arm, leg, foot, eye, ear, nose, mouth, hair, back, shoulder, knee, finger, heart
  Emotions: happy, sad, angry, scared, surprised, tired, excited, nervous, calm, proud, confused, bored
  Occupations: doctor, teacher, cook, driver, farmer, artist, musician, nurse, builder, student, shop assistant, waiter

Available themes:
  greeting, shopping, restaurant, directions, medical, school, work, family, hobbies, travel, weather, daily_routine

"Sarka" means "magpie" in Lithuanian - known for being talkative and social.
        """,
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
        help="Generate new conversations",
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

    # Generation options
    gen_group = parser.add_argument_group("Generation options")
    gen_group.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of conversations to generate (default: 1)",
    )
    gen_group.add_argument(
        "--colors",
        nargs="+",
        type=str,
        help="Specific colors to use (max 2)",
    )
    gen_group.add_argument(
        "--body-part",
        type=str,
        help="Specific body part to use",
    )
    gen_group.add_argument(
        "--emotion",
        type=str,
        help="Specific emotion to use",
    )
    gen_group.add_argument(
        "--occupation",
        type=str,
        help="Specific occupation to use",
    )
    gen_group.add_argument(
        "--theme",
        type=str,
        choices=CONVERSATION_THEMES,
        help="Specific theme to use",
    )
    gen_group.add_argument(
        "--num-sentences",
        type=int,
        default=6,
        help="Target number of sentences per conversation (default: 6)",
    )

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue work items for background processing by barsukas worker",
    )

    return parser


def validate_keywords(args) -> Dict:
    """Validate and build keywords dictionary from args.

    Args:
        args: Parsed command-line arguments

    Returns:
        Dictionary of validated keywords, or empty dict for random selection
    """
    keywords = {}

    if args.colors:
        # Validate colors
        invalid = [c for c in args.colors if c not in KEYWORD_CATEGORIES["colors"]]
        if invalid:
            logger.warning(f"Invalid colors ignored: {invalid}")
        valid_colors = [c for c in args.colors if c in KEYWORD_CATEGORIES["colors"]]
        if valid_colors:
            keywords["colors"] = valid_colors[:2]  # Max 2

    if args.body_part:
        if args.body_part in KEYWORD_CATEGORIES["body_parts"]:
            keywords["body_part"] = args.body_part
        else:
            logger.warning(f"Invalid body part ignored: {args.body_part}")

    if args.emotion:
        if args.emotion in KEYWORD_CATEGORIES["emotions"]:
            keywords["emotion"] = args.emotion
        else:
            logger.warning(f"Invalid emotion ignored: {args.emotion}")

    if args.occupation:
        if args.occupation in KEYWORD_CATEGORIES["occupations"]:
            keywords["occupation"] = args.occupation
        else:
            logger.warning(f"Invalid occupation ignored: {args.occupation}")

    if args.theme:
        keywords["theme"] = args.theme

    return keywords if keywords else None


def enqueue_conversation_work(agent: SarkaAgent, session, count: int, dry_run: bool = False):
    """Enqueue conversation generation work items to the queue.

    Args:
        agent: SarkaAgent instance
        session: Database session
        count: Number of conversations to generate
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    enqueued_count = 0

    logger.info(f"Enqueuing {count} conversation generation tasks...")
    if dry_run:
        logger.info("DRY RUN MODE - No work items will be enqueued")

    for i in range(count):
        # Select keywords for this task
        keywords = agent.select_keywords()

        if not dry_run:
            # Create a unique dedup key based on keywords
            import json
            import hashlib

            keywords_str = json.dumps(keywords, sort_keys=True)
            keywords_hash = hashlib.md5(keywords_str.encode()).hexdigest()[:8]
            dedup_key = f"sarka_generate_{keywords_hash}_{i}"

            result = enqueue_task(
                session,
                task_type="sarka_generate_conversation",
                target_type="conversation",
                target_id=None,
                payload={
                    "keywords": keywords,
                    "num_sentences": 6,
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
        "requested": count,
        "dry_run": dry_run,
    }


def get_sarka_queue_stats(session):
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


def main():
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
        print(f"Theme: {conversation['theme']}")
        print(f"Keywords: {', '.join(conversation['keywords'])}")
        print(f"Level: {conversation['minimum_level'] or 'Not calculated'}")
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

    # GENERATE MODE
    if args.generate:
        # Validate and build keywords
        keywords = validate_keywords(args)

        # WORKQUEUE MODE: Enqueue work for background processing
        if args.use_workqueue:
            logger.info("=" * 60)
            logger.info("SARKA AGENT - ENQUEUING WORK")
            logger.info("=" * 60)

            session = agent.get_session()
            try:
                results = enqueue_conversation_work(
                    agent=agent,
                    session=session,
                    count=args.count,
                    dry_run=args.dry_run,
                )

                print("\n" + "=" * 60)
                print("WORK ENQUEUE SUMMARY")
                print("=" * 60)
                print(f"Requested: {results['requested']}")
                print(f"Enqueued: {results['enqueued']}")
                if results["dry_run"]:
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

        if args.count == 1:
            # Single conversation
            result = agent.generate_conversation(
                keywords=keywords,
                num_sentences=args.num_sentences,
                dry_run=args.dry_run,
            )

            print("\n" + "=" * 60)
            print("CONVERSATION GENERATION RESULT")
            print("=" * 60)

            if result.get("error"):
                print(f"Error: {result['error']}")
                sys.exit(1)

            if result.get("dry_run"):
                print("[DRY RUN] Would generate:")
            else:
                print(f"Conversation ID: {result.get('conversation_id')}")

            print(f"Title: {result.get('title')}")
            print(f"Theme: {result.get('theme')}")
            print(f"Keywords: {result.get('keywords')}")
            print(f"Sentences: {result.get('num_sentences')}")

            print("\n--- Generated Conversation ---")
            for sent in result.get("sentences", []):
                print(f"[{sent['speaker']}] {sent['text']}")

            print("=" * 60)

        else:
            # Batch generation
            results = agent.generate_batch(
                count=args.count,
                dry_run=args.dry_run,
            )

            print("\n" + "=" * 60)
            print("BATCH GENERATION SUMMARY")
            print("=" * 60)
            print(f"Total requested: {results['total']}")
            print(f"Successful: {results['successful']}")
            print(f"Failed: {results['failed']}")
            if results["dry_run"]:
                print("\n[DRY RUN] No conversations were actually saved")
            print("=" * 60)

            # Show first few results
            print("\nSample results:")
            for i, res in enumerate(results["results"][:3], 1):
                if res.get("success") or res.get("dry_run"):
                    print(f"{i}. {res.get('title')} ({res.get('num_sentences')} sentences)")
                else:
                    print(f"{i}. Error: {res.get('error')}")

            if len(results["results"]) > 3:
                print(f"   ... and {len(results['results']) - 3} more")
            print("=" * 60)


if __name__ == "__main__":
    main()
