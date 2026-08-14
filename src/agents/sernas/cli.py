#!/usr/bin/env python3
"""
Šernas Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys
from typing import Any, Dict, List, Optional

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_level_args,
    add_llm_args,
    add_pos_type_args,
    add_processing_args,
    get_data_source_config,
)
from workqueue.task_queue import TaskType, enqueue_task, get_active_task


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Šernas - Synonym and Alternative Form Generator Agent"
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5.4-mini")
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_level_args(parser)
    add_pos_type_args(parser)
    add_language_args(parser)
    add_backend_args(parser)

    # Mode selection - mutually exclusive flags
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--coverage",
        action="store_true",
        help="Report missing synonyms/alternatives coverage (default mode)",
    )
    mode_group.add_argument(
        "--populate",
        action="store_true",
        help="Populate missing synonyms/alternatives",
    )
    mode_group.add_argument(
        "--regenerate",
        action="store_true",
        help="Delete and regenerate all synonyms/alternatives (destructive)",
    )
    parser.add_argument(
        "--type",
        choices=[
            "synonym",
            "abbreviation",
            "expanded_form",
            "all",
        ],
        help="[Check/Fix mode] Type to check/generate. Options: synonym, abbreviation, expanded_form, or all. Default: all",
    )

    # Override default languages to ['en']
    parser.set_defaults(languages=["en"])

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue work items for background processing by barsukas worker",
    )

    return parser


def enqueue_sernas_work(
    session: Any,
    lemmas: List[Any],
    languages: List[str],
    form_type: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Enqueue synonym generation work items to the queue.

    Args:
        session: Database session
        lemmas: List of lemmas to process
        languages: List of language codes to process
        form_type: Specific form type or None for all
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    enqueued_count = 0
    skipped_count = 0

    for lemma in lemmas:
        for language_code in languages:
            if not dry_run:
                form_key = form_type or "all"
                dedup_key = f"{TaskType.WORDS_SYNONYMS}:{lemma.id}:{language_code}:{form_key}"
                legacy_dedup_key = f"sernas_{lemma.id}_{language_code}_{form_key}"
                if get_active_task(session, legacy_dedup_key) is not None:
                    skipped_count += 1
                    continue
                result = enqueue_task(
                    session,
                    task_type=TaskType.WORDS_SYNONYMS,
                    target_type="lemma",
                    target_id=lemma.id,
                    payload={
                        "schema_version": 1,
                        "language_code": language_code,
                        "lemma_id": lemma.id,
                        "form_type": form_type,
                        "source_component": "agents.sernas",
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


def main() -> None:
    """Main entry point for the šernas agent."""
    from agents.common.cli_display import display_language_header
    from words.lemma_selection import get_lemmas_for_agent
    from agents.sernas.agent import SernasAgent
    from agents.sernas.cli_display import display_batch_results
    from storage.translation_helpers import (
        get_tier_1_and_tier_2_languages,
        normalize_llm_language_codes,
    )

    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args
    config = get_data_source_config(args)

    # Create agent with config
    agent = SernasAgent(config=config)

    # Get lemmas to process (either single lemma from --guid or batch)
    session = agent.get_session()
    try:
        lemmas = get_lemmas_for_agent(session, args)
    finally:
        session.close()

    # Convert --type argument to form_type
    form_type = None
    if args.type and args.type != "all":
        form_type = args.type

    # Get languages to process
    requested_all_languages = bool(args.languages and "all" in args.languages)
    languages_to_process = args.languages if args.languages else ["en"]
    languages_to_process = normalize_llm_language_codes(
        languages_to_process,
        operation_name="Sernas synonym generation",
        all_expansion=get_tier_1_and_tier_2_languages(),
    )

    # Determine mode from flags (default to coverage if none specified)
    if args.populate:
        mode = "populate"
    elif args.regenerate:
        mode = "regenerate"
    else:
        mode = "coverage"  # default

    # Handle coverage mode (report missing synonyms)
    if mode == "coverage":
        # Check specific languages or all languages
        if len(languages_to_process) == 1 or requested_all_languages:
            # Single language or all languages - use simpler report
            results = agent.check_missing_synonyms(
                lemmas=lemmas,
                language_code=languages_to_process[0] if len(languages_to_process) == 1 else None,
                form_type=form_type,
            )

            if "error" in results:
                print(f"Error: {results['error']}")
                return

            if len(languages_to_process) == 1:
                # Single language detailed report
                language_code = languages_to_process[0]
                missing = results["missing_by_language"].get(language_code, [])

                print(f"\n{'='*60}")
                print(f"ŠERNAS AGENT REPORT - {language_code.upper()}")
                print(f"{'='*60}")
                print(f"Lemmas missing forms: {len(missing)}")
                print(f"Checked form types: {', '.join(results['checked_form_types'])}")
                print("")

                if missing:
                    print("Sample lemmas needing forms:")
                    for i, lemma in enumerate(missing[:10], 1):
                        print(
                            f"  {i}. {lemma['english']} -> {lemma['translation']} ({lemma['pos_type']})"
                        )
                    if len(missing) > 10:
                        print(f"  ... and {len(missing) - 10} more")
                print(f"{'='*60}")
            else:
                # All languages summary
                print(f"\n{'='*60}")
                print("ŠERNAS AGENT REPORT - Synonyms and Alternative Forms Check")
                print(f"{'='*60}")
                print(f"Total lemmas missing forms: {results['total_missing']}")
                print(f"Checked form types: {', '.join(results['checked_form_types'])}")
                print("")

                for lang_code in results["checked_languages"]:
                    missing = results["missing_by_language"].get(lang_code, [])
                    print(f"{lang_code.upper()}: {len(missing)} lemmas missing forms")

                print(f"{'='*60}")
        else:
            # Multiple specific languages - show detail for each
            for language_code in languages_to_process:
                results = agent.check_missing_synonyms(
                    lemmas=lemmas, language_code=language_code, form_type=form_type
                )

                if "error" in results:
                    print(f"Error: {results['error']}")
                    continue

                missing = results["missing_by_language"].get(language_code, [])

                print(f"\n{'='*60}")
                print(f"ŠERNAS AGENT REPORT - {language_code.upper()}")
                print(f"{'='*60}")
                print(f"Lemmas missing forms: {len(missing)}")
                print(f"Checked form types: {', '.join(results['checked_form_types'])}")
                print("")

                if missing:
                    print("Sample lemmas needing forms:")
                    for i, lemma in enumerate(missing[:10], 1):
                        print(
                            f"  {i}. {lemma['english']} -> {lemma['translation']} ({lemma['pos_type']})"
                        )
                    if len(missing) > 10:
                        print(f"  ... and {len(missing) - 10} more")

                print(f"{'='*60}")
        return

    # WORKQUEUE MODE: Enqueue work items for barsukas worker
    if args.use_workqueue and mode in ["populate", "regenerate"]:
        print("\n" + "=" * 80)
        print("ŠERNAS AGENT - ENQUEUING WORK")
        print("=" * 80)

        session = agent.get_session()
        try:
            results = enqueue_sernas_work(
                session=session,
                lemmas=lemmas,
                languages=languages_to_process,
                form_type=form_type,
                dry_run=args.dry_run,
            )

            print(f"\nEnqueued: {results['enqueued']}")
            print(f"Skipped: {results['skipped']}")
            if results["dry_run"]:
                print("\n⚠️  DRY RUN - No work items were actually enqueued")
            print("=" * 80)
        finally:
            session.close()

        return

    # Handle populate mode
    if mode == "populate":
        # Process each language
        for lang_idx, language_code in enumerate(languages_to_process):
            display_language_header(language_code, lang_idx + 1, len(languages_to_process))

            # Confirmation prompt (unless --yes or --dry-run)
            if not args.yes and not args.dry_run:
                # Get check results to show how many need fixing
                check_results = agent.check_missing_synonyms(
                    lemmas=lemmas, language_code=language_code, form_type=form_type
                )

                if "error" in check_results:
                    print(f"Error checking synonyms: {check_results['error']}")
                    continue

                missing_count = len(check_results["missing_by_language"].get(language_code, []))

                print(f"\nReady to generate synonyms/alternatives for {language_code}")
                print(f"Lemmas needing forms: {missing_count}")
                print(
                    f"Will process: {min(args.limit, missing_count) if args.limit else missing_count}"
                )
                print(f"Model: {args.model}")
                print(f"Throttle: {args.throttle}s between calls")

                response = input("\nContinue? [y/N]: ")
                if response.lower() not in ["y", "yes"]:
                    print("Skipping this language.")
                    continue

            results = agent.fix_missing_synonyms(
                lemmas=lemmas,
                language_code=language_code,
                form_type=form_type,
                limit=args.limit,
                model=args.model,
                throttle=args.throttle,
                dry_run=args.dry_run,
            )

            # Print results
            display_batch_results(results, language_code, dry_run=args.dry_run)
        return

    # Handle regenerate mode (similar to populate but forces regeneration)
    if mode == "regenerate":
        from storage.crud.grammar_fact import delete_grammar_fact
        from storage.crud.operation_log import delete_synonym_scan_records

        # Process each language
        for lang_idx, language_code in enumerate(languages_to_process):
            display_language_header(language_code, lang_idx + 1, len(languages_to_process))

            # Delete existing grammar facts for all lemmas
            session = agent.get_session()
            try:
                for lemma in lemmas:
                    delete_grammar_fact(session, lemma.id, language_code, "has_abbreviations")
                    delete_grammar_fact(session, lemma.id, language_code, "has_expanded_forms")
                    delete_synonym_scan_records(session, lemma.id, language_code)
                session.commit()
            finally:
                session.close()

            # Confirmation prompt (unless --yes or --dry-run)
            if not args.yes and not args.dry_run:
                print(f"\nReady to regenerate synonyms/alternatives for {language_code}")
                print(f"Lemmas to process: {len(lemmas)}")
                print(f"Model: {args.model}")
                print(f"Throttle: {args.throttle}s between calls")

                response = input("\nContinue? [y/N]: ")
                if response.lower() not in ["y", "yes"]:
                    print("Skipping this language.")
                    continue

            # For regenerate, we want to process all lemmas (not just missing)
            results = agent.fix_missing_synonyms(
                lemmas=lemmas,
                language_code=language_code,
                form_type=form_type,
                limit=args.limit,
                model=args.model,
                throttle=args.throttle,
                dry_run=args.dry_run,
            )

            # Print results
            display_batch_results(results, language_code, dry_run=args.dry_run)
        return


if __name__ == "__main__":
    main()
