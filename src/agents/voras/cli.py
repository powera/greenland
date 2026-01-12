#!/usr/bin/env python3
"""
Voras Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_llm_args,
    add_output_args,
    add_processing_args,
    get_data_source_config,
    validate_cache_args,
)
from agents.common.lemma_selection import get_lemmas_for_agent
from barsukas.utils.task_queue import TaskStatus, enqueue_task
from wordfreq.storage.models.schema import BarsukasTask

# Import language mappings from translation_helpers (single source of truth)
from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Voras - Multi-lingual Translation Validator and Populator"
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_output_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_backend_args(parser)

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["check-only", "populate-only", "both", "coverage", "regenerate"],
        default="coverage",
        help="Operation mode: check-only (validate existing), populate-only (add missing), both (validate + populate), coverage (report only, default), regenerate (delete and regenerate, supports --batch)",
    )

    # Language selection (multiple)
    parser.add_argument(
        "--language",
        "--languages",
        nargs="+",
        dest="languages",
        choices=list(LANGUAGE_FIELDS.keys()),
        help="Specific language(s) to process (lt, zh, ko, fr, es, de, pt, sw, vi). Can specify multiple languages separated by spaces. If not specified, processes all languages.",
    )

    # Additional parameters
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Minimum confidence to flag issues (0.0-1.0, default: 0.7)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use batch mode (supported by --mode regenerate only): queue requests instead of making synchronous API calls",
    )
    parser.add_argument(
        "--batch-submit", action="store_true", help="Submit all pending batch requests to OpenAI"
    )

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue work items for background processing by barsukas worker instead of immediate processing",
    )

    return parser


def _handle_single_lemma_populate(agent, lemma, session, args):
    """Handle populate mode for a single lemma.

    Args:
        agent: VorasAgent instance
        lemma: Lemma object to process
        session: Database session
        args: Command-line arguments

    Returns:
        True if successful, False otherwise
    """
    from agents.voras import cli_display
    from wordfreq.storage.translation_helpers import (
        LANGUAGE_NAMES,
        convert_llm_response_to_lang_codes,
        get_reference_translation,
    )

    missing_langs = cli_display.display_lemma_translations(lemma, agent, session)

    if not missing_langs:
        print("\n✓ No missing translations")
        return True

    print(f"\nMissing translations: {', '.join(missing_langs)}")
    if args.dry_run:
        print("[DRY RUN] Would generate missing translations")
        return True

    print("Generating missing translations...")

    # Try cache first if available
    response = None
    cache_client = agent.get_cache_client()
    if cache_client:
        try:
            cached_translations = cache_client.get_translations(lemma.guid)
            if cached_translations:
                print("  Using cached translations from BARSUKAS server")
                response = cached_translations
        except Exception as cache_error:
            print(f"  Cache lookup failed: {cache_error}")
            if agent.config.cache_only:
                raise

    # If no cache hit, query LLM
    if not response:
        if agent.config.cache_only:
            print("\n✗ Cache-only mode: cannot generate translations (not in cache)")
            return False
        else:
            client = agent.get_linguistic_client()
            try:
                reference_lang_code, reference_translation = get_reference_translation(
                    session, lemma, exclude_languages=missing_langs
                )

                # If no reference translation, use English
                if not reference_translation:
                    reference_lang_code = "en"
                    reference_translation = lemma.lemma_text

                # Build list of missing language names for query_translations
                missing_lang_names = [
                    LANGUAGE_NAMES[lc].lower() for lc in missing_langs if lc in LANGUAGE_NAMES
                ]

                # Query translations
                llm_response, success = client.query_translations(
                    english_word=lemma.lemma_text,
                    reference_translation=(reference_lang_code, reference_translation),
                    definition=lemma.definition_text,
                    pos_type=lemma.pos_type,
                    pos_subtype=lemma.pos_subtype,
                    languages=missing_lang_names,
                )

                if success and llm_response:
                    # Convert LLM response to lang_code format
                    response = convert_llm_response_to_lang_codes(llm_response)
                else:
                    response = None

            except Exception as e:
                print(f"\nError generating translations: {e}")
                session.rollback()
                return False

    if response:
        cli_display.display_generated_translations(response, missing_langs)
        for lang_code in missing_langs:
            if lang_code in response and response[lang_code]:
                agent.set_translation(session, lemma, lang_code, response[lang_code])
        session.commit()
        print("\n✓ Translations saved")
        return True
    else:
        print("\nFailed to generate translations")
        return False


def enqueue_voras_populate_work(agent, session, lemmas, languages_to_fix, dry_run=False):
    """Enqueue translation population work items to the queue.

    Args:
        agent: VorasAgent instance
        session: Database session
        lemmas: List of lemmas to process
        languages_to_fix: List of language codes to generate translations for
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    enqueued_count = 0
    skipped_count = 0

    if dry_run:
        print("DRY RUN MODE - No work items will be enqueued")

    for lemma in lemmas:
        # Enqueue work item for each missing translation
        if not dry_run:
            dedup_key = f"voras_populate_{lemma.id}"
            result = enqueue_task(
                session,
                task_type="voras_populate_translations",
                target_type="lemma",
                target_id=lemma.id,
                payload={
                    "lemma_guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                    "languages": languages_to_fix,
                },
                dedup_key=dedup_key,
            )
            if result.created:
                enqueued_count += 1
            else:
                skipped_count += 1
        else:
            enqueued_count += 1

    if not dry_run:
        session.commit()

    return {
        "enqueued": enqueued_count,
        "skipped": skipped_count,
        "dry_run": dry_run,
    }


def enqueue_voras_regenerate_work(agent, session, lemmas, dry_run=False):
    """Enqueue translation regeneration work items to the queue.

    Args:
        agent: VorasAgent instance
        session: Database session
        lemmas: List of lemmas to process
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    enqueued_count = 0
    skipped_count = 0

    if dry_run:
        print("DRY RUN MODE - No work items will be enqueued")

    for lemma in lemmas:
        # Enqueue work item for regeneration
        if not dry_run:
            dedup_key = f"voras_regenerate_{lemma.id}"
            result = enqueue_task(
                session,
                task_type="voras_regenerate_translations",
                target_type="lemma",
                target_id=lemma.id,
                payload={
                    "lemma_guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                },
                dedup_key=dedup_key,
            )
            if result.created:
                enqueued_count += 1
            else:
                skipped_count += 1
        else:
            enqueued_count += 1

    if not dry_run:
        session.commit()

    return {
        "enqueued": enqueued_count,
        "skipped": skipped_count,
        "dry_run": dry_run,
    }


def get_voras_queue_stats(session):
    """Get statistics for voras tasks in the queue."""
    stats = {}
    for task_type in ["voras_populate_translations", "voras_regenerate_translations"]:
        stats[task_type] = {
            "pending": session.query(BarsukasTask).filter(
                BarsukasTask.task_type == task_type,
                BarsukasTask.status == TaskStatus.PENDING
            ).count(),
            "running": session.query(BarsukasTask).filter(
                BarsukasTask.task_type == task_type,
                BarsukasTask.status == TaskStatus.RUNNING
            ).count(),
            "completed": session.query(BarsukasTask).filter(
                BarsukasTask.task_type == task_type,
                BarsukasTask.status == TaskStatus.COMPLETED
            ).count(),
            "failed": session.query(BarsukasTask).filter(
                BarsukasTask.task_type == task_type,
                BarsukasTask.status == TaskStatus.FAILED
            ).count(),
        }
    return stats


def main():
    """Main entry point for the voras agent."""
    # Import here to avoid circular imports
    from agents.voras import cli_display
    from agents.voras.agent import VorasAgent
    from wordfreq.storage.models.schema import Lemma

    parser = get_argument_parser()
    args = parser.parse_args()

    # Validate cache arguments
    validate_cache_args(args)

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Create agent with unified configuration
    agent = VorasAgent(config=config)

    # Handle batch submit first (no lemmas needed)
    if args.batch_submit:
        agent.submit_batch()
        return

    # Handle coverage mode (no lemmas needed)
    if args.mode == "coverage":
        agent.run_full_check(output_file=args.output)
        return

    # Handle regenerate mode (operates on all curated lemmas, not --guid)
    if args.mode == "regenerate":
        # Confirmation for regenerate mode
        if not args.yes and not args.dry_run:
            session = agent.get_session()
            try:
                query = session.query(Lemma).filter(Lemma.guid.isnot(None))
                if args.limit:
                    query = query.limit(args.limit)
                word_count = query.count()

                print(f"\nREGENERATION MODE")
                print(f"This will:")
                print(f"  1. Delete all non-Lithuanian translations")
                if args.use_workqueue:
                    print(
                        f"  2. Enqueue {word_count} regeneration tasks for barsukas worker"
                    )
                elif args.batch:
                    print(
                        f"  2. Queue {word_count} batch requests (1 per word) for later submission"
                    )
                else:
                    print(
                        f"  2. Regenerate them fresh using {word_count} LLM API calls (1 per word)"
                    )
                print(f"\nModel: {args.model}")
                print(f"Words to process: {word_count}")

                response = input("Do you want to proceed? [y/N]: ").strip().lower()
                if response not in ["y", "yes"]:
                    print("Aborted.")
                    sys.exit(0)
            finally:
                session.close()

        # WORKQUEUE MODE: Enqueue work items for barsukas worker to process
        if args.use_workqueue:
            print("\n" + "=" * 80)
            print("VORAS AGENT - ENQUEUING REGENERATE WORK")
            print("=" * 80)

            session = agent.get_session()
            try:
                # Get lemmas to regenerate
                query = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id)
                if args.limit:
                    query = query.limit(args.limit)
                regenerate_lemmas = query.all()

                results = enqueue_voras_regenerate_work(
                    agent=agent,
                    session=session,
                    lemmas=regenerate_lemmas,
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
                    stats = get_voras_queue_stats(session)
                    print("\nCurrent queue status:")
                    for task_type, task_stats in stats.items():
                        if task_stats['pending'] + task_stats['running'] + task_stats['completed'] + task_stats['failed'] > 0:
                            print(f"\n  {task_type}:")
                            print(f"    Pending: {task_stats['pending']}")
                            print(f"    Running: {task_stats['running']}")
                            print(f"    Completed: {task_stats['completed']}")
                            print(f"    Failed: {task_stats['failed']}")
                    print("=" * 80)

            except Exception as e:
                print(f"Failed to enqueue work: {e}")
                sys.exit(1)
            finally:
                session.close()

            return

        # Execute regeneration (immediate or batch mode)
        results = agent.regenerate_all_translations(
            limit=args.limit, dry_run=args.dry_run, batch_mode=args.batch
        )
        cli_display.display_batch_summary(results, batch_mode=args.batch)
        return

    # Get lemmas to process (either single lemma from --guid or batch)
    # This handles both modes uniformly - returns a list with one or more lemmas
    session = agent.get_session()
    try:
        lemmas = get_lemmas_for_agent(session, args)
    finally:
        session.close()

    if len(lemmas) == 0:
        print(f"\nNo lemmas found to process")
        sys.exit(1)

    # Handle single lemma mode (from --guid) - provide detailed interactive experience
    if len(lemmas) == 1 and args.mode in ["populate-only", "both"]:
        lemma = lemmas[0]
        session = agent.get_session()
        try:
            _handle_single_lemma_populate(agent, lemma, session, args)
        finally:
            session.close()
        return

    # Batch processing mode - get confirmation before running
    if not args.yes and not args.dry_run and args.mode in ["check-only", "populate-only", "both"]:
        print(f"\nThis will process {len(lemmas)} lemmas using model '{args.model}'")
        print("This may incur costs and take some time to complete.")
        response = input("Do you want to proceed? [y/N]: ").strip().lower()
        if response not in ["y", "yes"]:
            print("Aborted.")
            sys.exit(0)

    # Execute the requested mode
    if args.mode == "check-only":
        # Validate existing translations
        languages_to_validate = args.languages if args.languages else list(LANGUAGE_FIELDS.keys())

        if len(languages_to_validate) == 1:
            results = agent.validate_translations(
                languages_to_validate[0],
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )
        else:
            results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )

        cli_display.display_validation_summary(results, languages_to_validate)

    elif args.mode == "populate-only":
        # Generate missing translations only

        # WORKQUEUE MODE: Enqueue work items for barsukas worker to process
        if args.use_workqueue:
            print("\n" + "=" * 80)
            print("VORAS AGENT - ENQUEUING POPULATE WORK")
            print("=" * 80)

            session = agent.get_session()
            try:
                languages_to_fix = args.languages if args.languages else list(LANGUAGE_FIELDS.keys())
                results = enqueue_voras_populate_work(
                    agent=agent,
                    session=session,
                    lemmas=lemmas,
                    languages_to_fix=languages_to_fix,
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
                    stats = get_voras_queue_stats(session)
                    print("\nCurrent queue status:")
                    for task_type, task_stats in stats.items():
                        if task_stats['pending'] + task_stats['running'] + task_stats['completed'] + task_stats['failed'] > 0:
                            print(f"\n  {task_type}:")
                            print(f"    Pending: {task_stats['pending']}")
                            print(f"    Running: {task_stats['running']}")
                            print(f"    Completed: {task_stats['completed']}")
                            print(f"    Failed: {task_stats['failed']}")
                    print("=" * 80)

            except Exception as e:
                print(f"Failed to enqueue work: {e}")
                sys.exit(1)
            finally:
                session.close()

            return

        # IMMEDIATE MODE: Process directly (default behavior)
        results = agent.fix_missing_translations(
            language_code=args.languages, limit=args.limit, dry_run=args.dry_run
        )
        cli_display.display_population_summary(results)

    elif args.mode == "both":
        # First validate, then populate
        languages_to_process = args.languages if args.languages else list(LANGUAGE_FIELDS.keys())

        print("\n=== STEP 1: Validating Existing Translations ===\n")
        if len(languages_to_process) == 1:
            validation_results = agent.validate_translations(
                languages_to_process[0],
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )
        else:
            validation_results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )

        print("\n=== STEP 2: Populating Missing Translations ===\n")
        population_results = agent.fix_missing_translations(
            language_code=args.languages, limit=args.limit, dry_run=args.dry_run
        )

        cli_display.display_combined_summary(
            validation_results, population_results, languages_to_process
        )


if __name__ == "__main__":
    main()
