#!/usr/bin/env python3
"""
Voras Agent - Command Line Interface

This module handles argument parsing, confirmation prompts, and display. The
translation work itself lives in :mod:`words.translation_workflow` (selection,
generation, storage, queueing) and :mod:`words.translation_coverage`
(reporting); queue mechanics live in :mod:`workqueue`.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, List

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_level_args,
    add_llm_args,
    add_output_args,
    add_pos_type_args,
    add_processing_args,
    get_data_source_config,
    parse_level_arg,
    validate_cache_args,
)
from words.lemma_selection import get_lemmas_for_agent
from workqueue.task_queue import TaskType


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Voras - Multi-lingual Translation Validator and Populator"
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser)
    add_output_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_level_args(parser)
    add_pos_type_args(parser)
    add_backend_args(parser)

    # Mode selection - mutually exclusive flags
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--coverage",
        action="store_true",
        help="Report translation coverage statistics (default mode)",
    )
    mode_group.add_argument(
        "--populate",
        action="store_true",
        help="Populate missing translations",
    )
    mode_group.add_argument(
        "--regenerate",
        action="store_true",
        help="Delete and regenerate all non-Lithuanian translations (destructive)",
    )

    add_language_args(parser)

    # Additional parameters
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


def _handle_single_lemma_populate(
    agent: Any, lemma: Any, session: Any, args: argparse.Namespace
) -> bool:
    """Populate one lemma interactively, showing each step.

    Args:
        agent: TranslationWorkflow instance
        lemma: Lemma object to process
        session: Database session
        args: Command-line arguments

    Returns:
        True if successful, False otherwise
    """
    from agents.voras import cli_display

    translations = agent.collect_translations(session, lemma)
    cli_display.display_lemma_translations(lemma, translations)
    missing_langs = [lang_code for lang_code, value in translations.items() if not value]

    if not missing_langs:
        print("\n✓ No missing translations")
        return True

    print(f"\nMissing translations: {', '.join(missing_langs)}")
    if args.dry_run:
        print("[DRY RUN] Would generate missing translations")
        return True

    print("Generating missing translations...")
    generated = agent.generate_translations_for_lemma(session, lemma, missing_langs)

    if not generated.translations:
        print(f"\n✗ {generated.error or 'Failed to generate translations'}")
        return False

    cli_display.display_generated_translations(generated.translations, missing_langs)
    agent.save_lemma_translations(
        session, lemma, generated.translations, missing_langs, source=generated.source
    )
    print("\n✓ Translations saved")
    return True


def _print_enqueue_results(session: Any, results: Any, dry_run: bool) -> None:
    """Print the enqueue summary and, for real runs, current queue depth."""
    from workqueue.stats import get_task_type_counts, has_queued_work

    print("\n" + "=" * 80)
    print("WORK ENQUEUE SUMMARY")
    print("=" * 80)
    print(f"Enqueued: {results['enqueued']}")
    print(f"Skipped: {results['skipped']}")
    if dry_run:
        print("\n⚠️  DRY RUN - No work items were actually enqueued")
    print("=" * 80)

    if dry_run:
        return

    stats = get_task_type_counts(
        session, [TaskType.WORDS_TRANSLATIONS, TaskType.WORDS_TRANSLATIONS_REGENERATE]
    )
    print("\nCurrent queue status:")
    for task_type, task_counts in stats.items():
        if not has_queued_work(task_counts):
            continue
        print(f"\n  {task_type}:")
        print(f"    Pending: {task_counts['pending']}")
        print(f"    Running: {task_counts['running']}")
        print(f"    Completed: {task_counts['completed']}")
        print(f"    Failed: {task_counts['failed']}")
    print("=" * 80)


def _confirm_regeneration(agent: Any, args: argparse.Namespace) -> bool:
    """Show what regeneration would do and ask whether to proceed."""
    from words.translation_workflow import count_curated_lemmas

    session = agent.get_session()
    try:
        word_count = count_curated_lemmas(session, args.limit)
    finally:
        session.close()

    print(f"\nREGENERATION MODE")
    print(f"This will:")
    print(f"  1. Delete all non-Lithuanian translations")
    if args.use_workqueue:
        print(f"  2. Enqueue {word_count} regeneration tasks for barsukas worker")
    elif args.batch:
        print(f"  2. Queue {word_count} batch requests (1 per word) for later submission")
    else:
        print(f"  2. Regenerate them fresh using {word_count} LLM API calls (1 per word)")
    print(f"\nModel: {args.model}")
    print(f"Words to process: {word_count}")

    response = input("Do you want to proceed? [y/N]: ").strip().lower()
    return response in ["y", "yes"]


def _run_regenerate(agent: Any, args: argparse.Namespace) -> None:
    """Regenerate every curated lemma's translations, or queue that work."""
    from agents.voras import cli_display
    from words.translation_workflow import (
        enqueue_translation_regeneration,
        select_curated_lemmas,
    )

    if not args.yes and not args.dry_run and not _confirm_regeneration(agent, args):
        print("Aborted.")
        sys.exit(0)

    # WORKQUEUE MODE: Enqueue work items for barsukas worker to process
    if args.use_workqueue:
        print("\n" + "=" * 80)
        print("VORAS AGENT - ENQUEUING REGENERATE WORK")
        print("=" * 80)

        session = agent.get_session()
        try:
            if args.dry_run:
                print("DRY RUN MODE - No work items will be enqueued")
            results = enqueue_translation_regeneration(
                session,
                select_curated_lemmas(session, args.limit),
                dry_run=args.dry_run,
            )
            _print_enqueue_results(session, results, args.dry_run)
        except Exception as e:
            print(f"Failed to enqueue work: {e}")
            sys.exit(1)
        finally:
            session.close()
        return

    results = agent.regenerate_all_translations(
        limit=args.limit, dry_run=args.dry_run, batch_mode=args.batch, lemmas=None
    )
    cli_display.display_batch_summary(results, batch_mode=args.batch)


def _run_populate(agent: Any, lemmas: List[Any], args: argparse.Namespace) -> None:
    """Generate the missing translations for the selected lemmas."""
    from agents.voras import cli_display
    from words.translation_workflow import (
        enqueue_translation_population,
        resolve_generation_languages,
    )

    # WORKQUEUE MODE: Enqueue work items for barsukas worker to process
    if args.use_workqueue:
        print("\n" + "=" * 80)
        print("VORAS AGENT - ENQUEUING POPULATE WORK")
        print("=" * 80)

        session = agent.get_session()
        try:
            if args.dry_run:
                print("DRY RUN MODE - No work items will be enqueued")
            results = enqueue_translation_population(
                session,
                lemmas,
                resolve_generation_languages(args.languages),
                dry_run=args.dry_run,
            )
            _print_enqueue_results(session, results, args.dry_run)
        except Exception as e:
            print(f"Failed to enqueue work: {e}")
            sys.exit(1)
        finally:
            session.close()
        return

    # IMMEDIATE MODE: Process directly (default behavior)
    results = agent.fix_missing_translations(
        language_code=args.languages, limit=args.limit, dry_run=args.dry_run, lemmas=lemmas
    )
    cli_display.display_population_summary(results)


def main() -> None:
    """Main entry point for the voras agent."""
    # Import here to avoid circular imports
    from words.translation_workflow import TranslationWorkflow

    parser = get_argument_parser()
    args = parser.parse_args()

    # Validate cache arguments
    validate_cache_args(args)

    # Validate that --batch and --use-workqueue aren't both set
    if args.batch and args.use_workqueue:
        print("Error: --batch and --use-workqueue cannot be used together")
        print("  --batch: Queue requests for OpenAI batch API")
        print("  --use-workqueue: Queue tasks for barsukas background worker")
        sys.exit(1)

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Create agent with unified configuration
    agent = TranslationWorkflow(config=config)

    # Determine mode from flags (default to coverage if none specified)
    if args.populate:
        mode = "populate"
    elif args.regenerate:
        mode = "regenerate"
    else:
        mode = "coverage"  # default

    # Handle batch submit first (no lemmas needed)
    if args.batch_submit:
        agent.submit_batch()
        return

    # Handle coverage mode (no lemmas needed)
    if mode == "coverage":
        # Parse level argument for coverage mode
        min_level, max_level = parse_level_arg(args.level)
        agent.run_full_check(
            output_file=args.output,
            min_level=min_level,
            max_level=max_level,
        )
        return

    # Handle regenerate mode (operates on all curated lemmas, not --guid)
    if mode == "regenerate":
        _run_regenerate(agent, args)
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
    if len(lemmas) == 1:
        lemma = lemmas[0]
        session = agent.get_session()
        try:
            _handle_single_lemma_populate(agent, lemma, session, args)
        finally:
            session.close()
        return

    # Batch processing mode - get confirmation before running
    if not args.yes and not args.dry_run:
        # Name the languages and the call count: "90 lemmas" alone reads as the
        # whole cost, but each word's languages are translated together in one
        # request, so the bill is words x batches, not words x languages.
        from storage.translation_helpers import split_llm_language_batches
        from words.translation_workflow import resolve_generation_languages

        languages = resolve_generation_languages(args.languages)
        batches = split_llm_language_batches(languages)
        calls = len(lemmas) * len(batches)
        per_word = (
            "1 LLM call per word covering all of them"
            if len(batches) == 1
            else f"{len(batches)} LLM calls per word, batched by language"
        )

        print(f"\nThis will process {len(lemmas)} lemmas using model '{args.model}'")
        print(f"Languages ({len(languages)}): {', '.join(languages)}")
        print(f"Translation is {per_word}, so ~{calls} LLM call(s) in total.")
        print("This may incur costs and take some time to complete.")
        response = input("Do you want to proceed? [y/N]: ").strip().lower()
        if response not in ["y", "yes"]:
            print("Aborted.")
            sys.exit(0)

    _run_populate(agent, lemmas, args)


if __name__ == "__main__":
    main()
