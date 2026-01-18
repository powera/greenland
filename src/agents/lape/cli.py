"""
Command-line interface for the Lape agent.

This module contains all CLI-related functionality including argument parsing,
work queue management, and the main entry point.
"""

import argparse
import json
import logging
import sys
from typing import Any, Dict, List

from sqlalchemy.orm import Session
from wordfreq.storage.models.schema import Lemma

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_level_args,
    add_llm_args,
    add_pos_type_args,
    get_data_source_config,
)
from agents.common.lemma_selection import get_lemmas_for_agent
from agents.lape.agent import LapeAgent
from barsukas.utils.task_queue import TaskStatus, enqueue_task
from wordfreq.storage.models.schema import BarsukasTask

logger = logging.getLogger(__name__)


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection."""
    parser = argparse.ArgumentParser(
        description="Lape - Grammar Facts Generator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate Chinese measure words for nouns
  python lape.py --fact-type measure_words --languages zh --limit 10

  # Generate French grammatical gender for nouns
  python lape.py --fact-type grammatical_gender --languages fr --limit 10

  # Generate verb transitivity (English-based, applies to all languages)
  python lape.py --fact-type verb_transitivity --languages en --limit 10

  # Generate French auxiliary verb classification (avoir/être)
  python lape.py --fact-type auxiliary_verb --languages fr --limit 10

  # Generate Lithuanian declension classes
  python lape.py --fact-type declension_class --languages lt --limit 10

  # Generate for a single lemma by GUID
  python lape.py --fact-type grammatical_gender --languages fr --guid N14_001

  # Dry run to see what would be generated
  python lape.py --fact-type grammatical_gender --languages fr --limit 5 --dry-run

  # Use grouped tasks to process multiple fact types
  python lape.py --task all --languages fr es --limit 10
  python lape.py --task nouns --languages lt en --limit 10
  python lape.py --task verbs --languages fr en --limit 10

Supported fact types:

  Noun facts:
    - measure_words: Chinese measure words/classifiers (languages: zh)
    - grammatical_gender: Noun gender (languages: fr, lt, es, de, pt, ru, it)
    - countability: Countable/uncountable/both (languages: en - base concept)
    - declension_class: Declension class 1-5 (languages: lt)
    - animacy: Animate/inanimate (languages: en - base concept)

  Verb facts:
    - verb_transitivity: Transitive/intransitive/ditransitive/ambitransitive (languages: en - base concept)
    - verb_reflexivity: Inherently/optionally/non-reflexive (languages: fr, es, de, lt, it)
    - auxiliary_verb: Compound tense auxiliary (languages: fr, de, it)

  Note: number_type (plurale_tantum/singulare_tantum) is auto-detected during form generation by Vilkas.

Task presets:
  - all: All fact types
  - gender: grammatical_gender only
  - measure-words: measure_words only
  - nouns: grammatical_gender, countability, animacy, declension_class
  - verbs: verb_transitivity, verb_reflexivity, auxiliary_verb
        """,
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_backend_args(parser)
    add_language_args(parser, multiple=True)

    # Lape-specific arguments
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_level_args(parser)
    add_pos_type_args(parser)
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument(
        "--fact-type",
        choices=LapeAgent.SUPPORTED_FACT_TYPES.keys(),
        help="Type of grammar fact to generate",
    )
    task_group.add_argument(
        "--task",
        choices=LapeAgent.TASK_PRESETS.keys(),
        help="Run a grouped task preset that maps to multiple fact types",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of lemmas to process")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip lemmas that already have this fact (default: True)",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Process all lemmas, even if they have existing facts",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence score to save fact (default: 0.7)",
    )

    # Mode selection - mutually exclusive flags
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--coverage",
        action="store_true",
        help="Report grammar facts coverage statistics (default mode)",
    )
    mode_group.add_argument(
        "--populate",
        action="store_true",
        help="Populate missing grammar facts",
    )

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue work items for background processing by barsukas worker instead of immediate processing",
    )

    return parser


def enqueue_grammar_fact_work(
    agent: LapeAgent,
    session: Session,
    lemmas: List[Lemma],
    fact_types_by_language: Dict[str, List[str]],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Enqueue grammar fact generation work items to the queue.

    Args:
        agent: LapeAgent instance
        session: Database session
        lemmas: List of lemmas to process
        fact_types_by_language: Dict mapping language_code to list of fact_types
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    enqueued_count = 0
    skipped_count = 0

    logger.info(f"Enqueuing work for {len(lemmas)} lemmas...")
    if dry_run:
        logger.info("DRY RUN MODE - No work items will be enqueued")

    for language_code, fact_types in fact_types_by_language.items():
        for fact_type in fact_types:
            fact_config = LapeAgent.SUPPORTED_FACT_TYPES[fact_type]
            required_pos = fact_config["required_pos"]

            for lemma in lemmas:
                # Skip if wrong POS type
                if lemma.pos_type not in required_pos:
                    skipped_count += 1
                    continue

                # Enqueue work item using barsukas task queue
                if not dry_run:
                    dedup_key = f"lape_{fact_type}_{lemma.id}_{language_code}"
                    result = enqueue_task(
                        session,
                        task_type="lape_generate_grammar_fact",
                        target_type="lemma",
                        target_id=lemma.id,
                        payload={
                            "fact_type": fact_type,
                            "language_code": language_code,
                            "lemma_guid": lemma.guid,
                            "lemma_text": lemma.lemma_text,
                        },
                        dedup_key=dedup_key,
                    )
                    if result.created:
                        enqueued_count += 1
                    else:
                        skipped_count += 1
                        logger.debug(
                            f"Skipped duplicate: {lemma.lemma_text} ({fact_type}, {language_code})"
                        )
                else:
                    enqueued_count += 1

    if not dry_run:
        session.commit()

    return {
        "enqueued": enqueued_count,
        "skipped": skipped_count,
        "dry_run": dry_run,
    }


def get_lape_queue_stats(session: Session) -> Dict[str, int]:
    """Get statistics for lape tasks in the queue."""
    task_type = "lape_generate_grammar_fact"
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
    """Command-line interface for the Lape agent."""
    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args
    config = get_data_source_config(args)

    # Create agent
    agent = LapeAgent(config=config)

    # Check required arguments
    if not args.languages:
        parser.error("At least one --language/--languages value is required")

    # Normalize language list while preserving order
    languages = list(dict.fromkeys(args.languages))

    explicit_fact_type = args.fact_type is not None

    # Determine which fact types to run (either explicit type or grouped task)
    if explicit_fact_type:
        fact_types_to_run = [args.fact_type]
    else:
        fact_types_to_run = LapeAgent.TASK_PRESETS[args.task]

    # Build fact_types_by_language map
    fact_types_by_language = {}
    for language_code in languages:
        applicable_fact_types = [
            fact_type
            for fact_type in fact_types_to_run
            if language_code in LapeAgent.SUPPORTED_FACT_TYPES[fact_type]["languages"]
        ]

        if explicit_fact_type and not applicable_fact_types:
            parser.error(
                f"Fact type '{args.fact_type}' does not support language '{language_code}'."
            )

        if applicable_fact_types:
            fact_types_by_language[language_code] = applicable_fact_types

    if not fact_types_by_language:
        logger.error("No applicable fact types for the selected languages")
        sys.exit(1)

    # Get lemmas to process (either single lemma from --guid or batch)
    session = agent.get_session()
    try:
        lemmas = get_lemmas_for_agent(session, args)
    finally:
        session.close()

    # Show what we're processing
    if len(lemmas) == 1:
        lemma = lemmas[0]
        logger.info(f"Processing: {lemma.lemma_text} (GUID: {lemma.guid}, POS: {lemma.pos_type})")
    elif len(lemmas) == 0:
        logger.error("No lemmas found to process")
        sys.exit(1)
    else:
        logger.info(f"Processing {len(lemmas)} lemmas")

    # Determine mode from flags (default to coverage if none specified)
    if args.populate:
        mode = "populate"
    else:
        mode = "coverage"  # default

    # COVERAGE MODE: Report what grammar facts are missing
    if mode == "coverage":
        from wordfreq.storage.crud.grammar_fact import get_grammar_fact_value

        logger.info("=" * 80)
        logger.info("LAPE AGENT - COVERAGE REPORT")
        logger.info("=" * 80)

        session = agent.get_session()
        try:
            for language_code, applicable_fact_types in fact_types_by_language.items():
                for fact_type in applicable_fact_types:
                    fact_config = LapeAgent.SUPPORTED_FACT_TYPES[fact_type]
                    required_pos = fact_config["required_pos"]

                    # Filter lemmas by POS type
                    matching_lemmas = [l for l in lemmas if l.pos_type in required_pos]

                    # Count missing
                    missing_count = 0
                    for lemma in matching_lemmas:
                        existing = get_grammar_fact_value(
                            session, lemma.id, language_code, fact_type
                        )
                        if existing is None:
                            missing_count += 1

                    print(
                        f"{fact_type} ({language_code}): {missing_count}/{len(matching_lemmas)} missing"
                    )
        finally:
            session.close()

        return

    # WORKQUEUE MODE: Enqueue work items for barsukas worker to process
    if args.use_workqueue and mode == "populate":
        logger.info("=" * 80)
        logger.info("LAPE AGENT - ENQUEUING WORK")
        logger.info("=" * 80)

        session = agent.get_session()
        try:
            results = enqueue_grammar_fact_work(
                agent=agent,
                session=session,
                lemmas=lemmas,
                fact_types_by_language=fact_types_by_language,
                dry_run=args.dry_run,
            )

            # Print summary
            print("\n" + "=" * 80)
            print("WORK ENQUEUE SUMMARY")
            print("=" * 80)
            print(f"Enqueued: {results['enqueued']}")
            print(f"Skipped: {results['skipped']}")
            if results["dry_run"]:
                print("\n⚠️  DRY RUN - No work items were actually enqueued")
            print("=" * 80)

            # Show queue stats
            if not args.dry_run:
                stats = get_lape_queue_stats(session)
                print("\nCurrent queue status:")
                print(f"  Pending: {stats['pending']}")
                print(f"  Running: {stats['running']}")
                print(f"  Completed: {stats['completed']}")
                print(f"  Failed: {stats['failed']}")
                print("=" * 80)

        except Exception as e:
            logger.error(f"Failed to enqueue work: {e}")
            sys.exit(1)
        finally:
            session.close()

        return

    # IMMEDIATE MODE: Process directly (default behavior)
    logger.info("=" * 80)
    logger.info("LAPE AGENT - IMMEDIATE PROCESSING")
    logger.info("=" * 80)

    try:
        for language_code, applicable_fact_types in fact_types_by_language.items():
            for fact_type in applicable_fact_types:
                results = agent.generate_grammar_facts(
                    fact_type=fact_type,
                    language_code=language_code,
                    lemmas=lemmas,
                    limit=args.limit,
                    skip_existing=args.skip_existing,
                    min_confidence=args.min_confidence,
                    dry_run=args.dry_run,
                )

                # Print summary
                print("\n" + "=" * 60)
                print("GRAMMAR FACTS GENERATION SUMMARY")
                print("=" * 60)
                print(f"Fact Type: {results['fact_type']}")
                print(f"Language: {results['language_code']}")
                print(f"Processed: {results['processed']}")
                print(f"Success: {results['success']}")
                print(f"Failed: {results['failed']}")
                print(f"Skipped: {results['skipped']}")
                if results["dry_run"]:
                    print("\n⚠️  DRY RUN - No changes saved to database")
                print("=" * 60)

                # Print some examples
                if results["results"]:
                    print("\nSample results:")
                    for i, result in enumerate(results["results"][:5], 1):
                        print(f"{i}. {result['lemma_text']} ({result['translation']})")
                        print(f"   → {result['fact_value']}")
                        print(f"   Confidence: {result['confidence']:.2f}")
                        if result["notes"]:
                            print(f"   Notes: {result['notes']}")

    except Exception as e:
        logger.error(f"Failed to generate grammar facts: {e}")
        sys.exit(1)
