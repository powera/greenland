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
from storage.models.schema import Lemma

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
from words.grammar_fact_tasks import FACT_TASKS
from words.grammar_facts import GrammarFactService
from words.grammar_fact_tasks.english_principal_parts import (
    ENGLISH_PRINCIPAL_PARTS_TASK,
    PRINCIPAL_PART_FACT_TYPES,
    principal_parts_coverage,
)
from words.lemma_selection import get_lemmas_for_agent
from workqueue.llm_batch import DEFAULT_ITEMS_PER_BATCH
from workqueue.task_queue import TaskStatus, TaskType, enqueue_task, get_active_task
from storage.models.schema import BarsukasTask

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

  # Generate ornamental English animal collectives (a murder of crows)
  python lape.py --fact-type fanciful_collective --languages en --limit 10

  # Generate English past and past participle together
  python lape.py --task english-principal-parts --languages en --limit 10

  # Generate for a single lemma by GUID
  python lape.py --fact-type grammatical_gender --languages fr --guid N14_001

  # Dry run to see what would be generated
  python lape.py --fact-type grammatical_gender --languages fr --limit 5 --dry-run

  # Send French genders as OpenAI batches (half price, results within 24h)
  python lape.py --fact-type grammatical_gender --languages fr --populate --batch

  # Use grouped tasks to process multiple fact types
  python lape.py --task all --languages fr es --limit 10
  python lape.py --task nouns --languages lt en --limit 10
  python lape.py --task verbs --languages fr en --limit 10

Supported fact types:

  Noun facts:
    - measure_words: Chinese measure words/classifiers (languages: zh)
    - grammatical_gender: Noun gender (languages: fr, lt, es, es-419, de, pt, it;
      run es before es-419, which copies es's fact when the word is the same)
    - countability: English noun usage (countable/uncountable/both; language: en)
    - declension_class: Declension class 1-5 (languages: lt)
    - animacy: Animate/inanimate (languages: en - base concept)
    - fanciful_collective: Ornamental animal collective, e.g. a murder of crows
      (languages: en); most animals have none, and none is a valid answer

  Verb facts:
    - verb_transitivity: Transitive/intransitive/ditransitive/ambitransitive (languages: en - base concept)
    - verb_reflexivity: Inherently/optionally/non-reflexive (languages: fr, es, de, lt, it)
    - auxiliary_verb: Compound tense auxiliary (languages: fr, de, it, nl)

  Note: every fact type above is exported to data/release except declension_class,
  which langtools.lt.declension recomputes from the noun plus its gender. Generating
  one of the others writes data that ships, so a rerun is not free.

  Facts that ship but no agent generates (hand-curated overrides): irregular plural,
  number_type (including a checked regular paradigm), French feminine_form,
  comparative, superlative, gradability, and
  the Lithuanian/Italian principal parts. English past and past_participle are
  generated together by the english-principal-parts task.

Task presets:
  - all: All fact types
  - gender: grammatical_gender only
  - measure-words: measure_words only
  - fanciful-collectives: fanciful_collective only
  - nouns: grammatical_gender, countability, animacy, declension_class
  - verbs: verb_transitivity, verb_reflexivity, auxiliary_verb
  - english-principal-parts: English past + past_participle in one model call
        """,
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser)
    add_backend_args(parser)
    add_language_args(parser)

    # Lape-specific arguments
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_level_args(parser)
    add_pos_type_args(parser)
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument(
        "--fact-type",
        choices=GrammarFactService.SUPPORTED_FACT_TYPES.keys(),
        help="Type of grammar fact to generate",
    )
    task_group.add_argument(
        "--task",
        choices=GrammarFactService.TASK_PRESETS.keys(),
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
    parser.add_argument(
        "--batch",
        action="store_true",
        help=(
            "With --populate: send the requests as OpenAI batches (half price); the "
            "Barsukas batch poller writes the results when each batch completes"
        ),
    )
    parser.add_argument(
        "--items-per-batch",
        type=int,
        default=DEFAULT_ITEMS_PER_BATCH,
        help=f"With --batch: requests per OpenAI batch (default: {DEFAULT_ITEMS_PER_BATCH})",
    )

    return parser


def enqueue_grammar_fact_work(
    agent: GrammarFactService,
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
            fact_config = GrammarFactService.get_fact_config(fact_type)
            required_pos = fact_config["required_pos"]

            for lemma in lemmas:
                # Skip if wrong POS type
                if lemma.pos_type not in required_pos:
                    skipped_count += 1
                    continue

                # Enqueue work item using barsukas task queue
                if not dry_run:
                    dedup_key = (
                        f"{TaskType.WORDS_GRAMMAR_FACTS}:{lemma.id}:" f"{language_code}:{fact_type}"
                    )
                    legacy_dedup_key = f"lape_{fact_type}_{lemma.id}_{language_code}"
                    prior_barsukas_dedup_key = (
                        f"{TaskType.WORDS_GRAMMAR_FACTS}:{lemma.id}:" f"{fact_type}:{language_code}"
                    )
                    if (
                        get_active_task(session, legacy_dedup_key) is not None
                        or get_active_task(session, prior_barsukas_dedup_key) is not None
                    ):
                        skipped_count += 1
                        continue
                    result = enqueue_task(
                        session,
                        task_type=TaskType.WORDS_GRAMMAR_FACTS,
                        target_type="lemma",
                        target_id=lemma.id,
                        payload={
                            "schema_version": 1,
                            "fact_type": fact_type,
                            "language_code": language_code,
                            "lemma_id": lemma.id,
                            "source_component": "agents.lape",
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


def _is_openai_model(model: str) -> bool:
    """Whether *model* is served by OpenAI, whose Batch API --batch uses."""
    return model.startswith(("gpt-", "o1", "o3", "o4"))


def _run_populate_batch(
    agent: GrammarFactService,
    lemmas: List[Lemma],
    fact_types_by_language: Dict[str, List[str]],
    args: argparse.Namespace,
) -> None:
    """Plan the missing facts, confirm, and send them as OpenAI batches."""
    from clients.batch_queue import BatchQueueManager, create_batch_database_session
    from clients.openai.batch_client import OpenAIBatchClient
    from workqueue.handlers.words.grammar_facts import GRAMMAR_FACT_JOB, grammar_fact_state
    from workqueue.llm_batch import start_batch_run

    states = [
        grammar_fact_state(lemma.id, language_code, fact_type, args.min_confidence)
        for language_code, fact_types in fact_types_by_language.items()
        for fact_type in fact_types
        for lemma in lemmas
        if lemma.pos_type in GrammarFactService.get_fact_config(fact_type)["required_pos"]
    ]

    batch_session = create_batch_database_session()
    session = agent.get_session()
    try:
        manager = BatchQueueManager(batch_session, OpenAIBatchClient())
        # Plan first without writing anything, so the counts can be confirmed.
        plan = start_batch_run(session, manager, GRAMMAR_FACT_JOB, states, args.model, dry_run=True)
        batches = -(-plan.calls // args.items_per_batch) if plan.calls else 0
        print("\n" + "=" * 80)
        print("LAPE AGENT - BATCH POPULATE")
        print("=" * 80)
        print(f"Model: {args.model}")
        for language_code, fact_types in fact_types_by_language.items():
            print(f"  {language_code}: {', '.join(fact_types)}")
        print(f"Items considered: {plan.items}")
        print(f"  already in a batch run: {plan.skipped_in_flight}")
        for outcome, count in sorted(plan.resolved_without_llm.items()):
            print(f"  {outcome} without a model call: {count}")
        print(f"Requests: {plan.calls} in {batches} batch(es) of up to {args.items_per_batch}")
        print("=" * 80)

        if not plan.calls and not plan.resolved_without_llm.get("answered"):
            print("Nothing to submit.")
            return
        if args.dry_run:
            print("DRY RUN - nothing was written, queued or submitted")
            return
        if plan.calls and not args.yes:
            response = input("Submit these batches to OpenAI? [y/N]: ").strip().lower()
            if response not in ["y", "yes"]:
                print("Aborted.")
                sys.exit(0)

        report = start_batch_run(
            session,
            manager,
            GRAMMAR_FACT_JOB,
            states,
            args.model,
            items_per_batch=args.items_per_batch,
        )
        print(f"Run {report.run_id}: {report.calls} request(s)")
        for batch_id in report.batch_ids:
            print(f"  submitted {batch_id}")
        if report.batch_ids:
            print("\nThe Barsukas batch poller checks every 5 minutes and writes the results.")
            print("By hand: python -m agents.common.batch status --batch-id <id>")
            print("         python -m agents.common.batch complete --batch-id <id>")
    finally:
        session.close()
        batch_session.close()


def get_lape_queue_stats(session: Session) -> Dict[str, int]:
    """Get statistics for lape tasks in the queue."""
    task_type = "words.grammar_facts"
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
    agent = GrammarFactService(config=config)

    # Check required arguments
    if not args.languages:
        parser.error("At least one --languages value is required")

    if args.batch and not args.populate:
        parser.error("--batch only applies with --populate")
    if args.batch and args.use_workqueue:
        parser.error("--batch and --use-workqueue cannot be used together")
    if args.batch and not _is_openai_model(args.model):
        parser.error(
            f"--batch uses the OpenAI Batch API; --model {args.model} is not an OpenAI model"
        )

    # Normalize language list while preserving order
    languages = list(dict.fromkeys(args.languages))

    explicit_fact_type = args.fact_type is not None

    # Determine which fact types to run (either explicit type or grouped task)
    if explicit_fact_type:
        fact_types_to_run = [args.fact_type]
    else:
        fact_types_to_run = GrammarFactService.TASK_PRESETS[args.task]

    if ENGLISH_PRINCIPAL_PARTS_TASK in fact_types_to_run:
        if args.pos_type not in (None, "verb"):
            parser.error("english-principal-parts only applies to --pos-type verb")
        # Apply the POS filter before the shared lemma selector applies --limit;
        # otherwise a small batch can be consumed entirely by non-verbs.
        args.pos_type = "verb"

    # Build fact_types_by_language map
    fact_types_by_language = {}
    for language_code in languages:
        applicable_fact_types = [
            fact_type
            for fact_type in fact_types_to_run
            if language_code in GrammarFactService.get_fact_config(fact_type)["languages"]
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

    if args.batch:
        unbatchable = sorted(
            {
                fact_type
                for fact_types in fact_types_by_language.values()
                for fact_type in fact_types
                if fact_type not in FACT_TASKS
            }
        )
        if unbatchable:
            parser.error(f"--batch does not support: {', '.join(unbatchable)}")

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
        from storage.crud.grammar_fact import get_grammar_fact_value

        logger.info("=" * 80)
        logger.info("LAPE AGENT - COVERAGE REPORT")
        logger.info("=" * 80)

        session = agent.get_session()
        try:
            for language_code, applicable_fact_types in fact_types_by_language.items():
                for fact_type in applicable_fact_types:
                    fact_config = GrammarFactService.get_fact_config(fact_type)
                    required_pos = fact_config["required_pos"]

                    # Filter lemmas by POS type
                    matching_lemmas = [l for l in lemmas if l.pos_type in required_pos]

                    # Count missing
                    missing_count = 0
                    for lemma in matching_lemmas:
                        if fact_type == ENGLISH_PRINCIPAL_PARTS_TASK or fact_type in (
                            PRINCIPAL_PART_FACT_TYPES
                        ):
                            if not all(principal_parts_coverage(session, lemma).values()):
                                missing_count += 1
                            continue
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

    # BATCH MODE: Send the requests as OpenAI batches
    if args.batch:
        _run_populate_batch(agent, lemmas, fact_types_by_language, args)
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
