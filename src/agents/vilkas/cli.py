#!/usr/bin/env python3
"""
Vilkas Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

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
    validate_cache_args,
)

# Define supported languages and their forms (matches agent.py SUPPORTED_LANGUAGES)
SUPPORTED_TASKS = {
    "lt": ["noun", "verb", "adjective", "adverb"],
    "fr": ["noun", "verb"],
    "de": ["noun", "verb"],
    "es": ["noun", "verb"],
    "pt": ["noun", "verb"],
    "en": ["noun", "verb", "adjective", "adverb"],
}

# Language names for display
LANGUAGE_NAMES = {
    "lt": "Lithuanian",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "en": "English",
}


def get_argument_parser() -> argparse.ArgumentParser:
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(description="Vilkas - Lithuanian Word Forms Checker Agent")

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_output_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_level_args(parser)
    add_pos_type_args(parser)
    add_language_args(parser, multiple=True)
    add_backend_args(parser)

    # Build task choices dynamically from module-level SUPPORTED_TASKS
    task_choices = []
    for lang, pos_types in SUPPORTED_TASKS.items():
        for pos in pos_types:
            if pos == "noun":
                # Use "declensions" for languages with case systems (LT, DE)
                # Use "forms" for languages without cases (EN, FR, ES, PT)
                if lang in ["lt", "de"]:
                    task_choices.append(f"{lang}-noun-declensions")
                else:
                    task_choices.append(f"{lang}-noun-forms")
            elif pos == "verb":
                task_choices.append(f"{lang}-verb-conjugations")
            elif pos == "adjective":
                task_choices.append(f"{lang}-adjective-forms")
            elif pos == "adverb":
                task_choices.append(f"{lang}-adverb-forms")
    task_choices.append("all")

    # Task selection - explicit language/form combinations
    parser.add_argument(
        "--task",
        choices=task_choices,
        help=(
            "Specific task to perform (language + form type). "
            "Supported: Lithuanian (noun-declensions/verb/adjective/adverb), "
            "French/Spanish/Portuguese (noun-forms/verb), "
            "German (noun-declensions/verb), "
            "English (noun-forms/verb/adjective/adverb). "
            "Use 'all' to process all supported forms."
        ),
    )

    # Mode selection - mutually exclusive flags
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--coverage",
        action="store_true",
        help="Report word forms coverage statistics (default mode)",
    )
    mode_group.add_argument(
        "--populate",
        action="store_true",
        help="Populate missing word forms",
    )

    # Workqueue arguments
    parser.add_argument(
        "--use-workqueue",
        action="store_true",
        default=False,
        help="Enqueue work items for background processing by barsukas worker",
    )

    # Form source arguments
    parser.add_argument(
        "--use-wiktionary",
        action="store_true",
        default=False,
        help="Use Wiktionary instead of LLM for form generation (no API cost, supports en/es/fr/lt)",
    )

    return parser


def enqueue_vilkas_work(
    session: Any, lemmas: List[Any], task: str, dry_run: bool = False
) -> Dict[str, Any]:
    """Enqueue word form generation work items to the queue.

    Args:
        session: Database session
        lemmas: List of lemmas to process
        task: Task string (e.g., 'lt-noun-declensions') or 'all'
        dry_run: If True, don't actually enqueue

    Returns:
        Dictionary with enqueue statistics
    """
    from workqueue.task_queue import enqueue_task

    enqueued_count = 0
    skipped_count = 0

    # Build list of (language, pos) tuples to process
    if task == "all":
        tasks_to_run = []
        for lang, pos_types in SUPPORTED_TASKS.items():
            for pos in pos_types:
                tasks_to_run.append((lang, pos))
    else:
        # Parse task string
        parts = task.split("-")
        lang = parts[0]
        pos = parts[1]  # noun, verb, adjective, adverb
        tasks_to_run = [(lang, pos)]

    for lemma in lemmas:
        for lang, pos in tasks_to_run:
            # Skip if POS doesn't match
            if lemma.pos_type != pos:
                skipped_count += 1
                continue

            if not dry_run:
                dedup_key = f"vilkas_{lang}_{pos}_{lemma.id}"
                result = enqueue_task(
                    session,
                    task_type="vilkas_generate_forms",
                    target_type="lemma",
                    target_id=lemma.id,
                    payload={
                        "language_code": lang,
                        "pos_type": pos,
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


def main() -> None:
    """Main entry point for the vilkas agent."""
    # Import here to avoid circular imports
    from agents.common.cli_display import display_language_header
    from agents.common.lemma_selection import get_lemmas_for_agent
    from agents.vilkas import display
    from agents.vilkas.agent import VilkasAgent

    parser = get_argument_parser()
    args = parser.parse_args()

    selected_languages = list(SUPPORTED_TASKS.keys())
    if args.languages:
        selected_languages = []
        unsupported_languages = []

        for lang in args.languages:
            lang_code = lang.lower()
            if lang_code in SUPPORTED_TASKS:
                if lang_code not in selected_languages:
                    selected_languages.append(lang_code)
            else:
                unsupported_languages.append(lang_code)

        if unsupported_languages:
            print(
                "Warning: Skipping unsupported languages: "
                + ", ".join(sorted(set(unsupported_languages)))
            )

        if not selected_languages:
            print("Error: None of the provided languages are supported by Vilkas")
            sys.exit(1)

    # Validate cache arguments
    validate_cache_args(args)

    # Create data source configuration (includes backend, cache, and LLM model)
    config = get_data_source_config(args, default_model="gpt-5-mini")

    # Create agent with unified configuration
    agent = VilkasAgent(config=config)

    # Require --task
    if not args.task:
        print("\nError: --task is required")
        print("Examples:")
        print("  --task lt-noun-declensions              # Check Lithuanian nouns")
        print("  --task lt-noun-declensions --fix        # Generate Lithuanian nouns")
        print("  --task all --fix                        # Generate all forms")
        print("  --guid N06_015 --task all               # Check all languages for specific lemma")
        print("  --guid N06_015 --task all --fix         # Generate all forms for specific lemma")
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
        print(f"\nProcessing word forms for: {lemma.lemma_text} (GUID: {lemma.guid})")
        print(f"POS: {lemma.pos_type}")
    elif len(lemmas) == 0:
        print(f"\nNo lemmas found to process")
        sys.exit(1)

    # Determine mode from flags (default to coverage if none specified)
    if args.populate:
        mode = "populate"
    else:
        mode = "coverage"  # default

    # Handle populate mode
    if mode == "populate":
        # Parse --task parameter to get language and form type
        language_code = None
        inferred_pos_type = None
        form_type_label = "forms"

        # Task parameter determines language and POS
        if args.task and args.task != "all":
            # Parse task string: "{lang}-{type}-{suffix}"
            # e.g., "lt-noun-declensions", "fr-verb-conjugations", "lt-adjective-forms"
            parts = args.task.split("-")
            if len(parts) >= 2:
                language_code = parts[0]
                form_category = parts[1]  # noun, verb, adjective

                # Map form category to POS type and label
                if form_category == "noun":
                    inferred_pos_type = "noun"
                    # Use "declensions" for case languages (LT, DE), "forms" for others
                    if language_code in ["lt", "de"]:
                        form_type_label = (
                            f"{LANGUAGE_NAMES.get(language_code, language_code)} noun declensions"
                        )
                    else:
                        form_type_label = (
                            f"{LANGUAGE_NAMES.get(language_code, language_code)} noun forms"
                        )
                elif form_category == "verb":
                    inferred_pos_type = "verb"
                    form_type_label = (
                        f"{LANGUAGE_NAMES.get(language_code, language_code)} verb conjugations"
                    )
                elif form_category == "adjective":
                    inferred_pos_type = "adjective"
                    form_type_label = (
                        f"{LANGUAGE_NAMES.get(language_code, language_code)} adjective forms"
                    )
                elif form_category == "adverb":
                    inferred_pos_type = "adverb"
                    form_type_label = (
                        f"{LANGUAGE_NAMES.get(language_code, language_code)} adverb forms"
                    )
        elif args.task == "all":
            language_code = None  # Process all languages
            if args.languages:
                form_type_label = f"all forms ({', '.join(selected_languages)})"
            else:
                form_type_label = "all forms (all languages)"
        elif args.languages and language_code not in selected_languages:
            print(
                f"Error: Language '{language_code}' is not included in --languages: "
                f"{', '.join(selected_languages)}"
            )
            sys.exit(1)

        # WORKQUEUE MODE: Enqueue work items for barsukas worker
        if args.use_workqueue:
            print("\n" + "=" * 80)
            print("VILKAS AGENT - ENQUEUING WORK")
            print("=" * 80)

            session = agent.get_session()
            try:
                results = enqueue_vilkas_work(
                    session=session,
                    lemmas=lemmas,
                    task=args.task,
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

        # Confirmation prompt (unless --yes or --dry-run)
        if not args.yes and not args.dry_run:
            # Get appropriate check results for confirmation
            language_names = {"lt": "Lithuanian", "fr": "French"}
            lang_name = (
                language_names.get(language_code, language_code.upper()) if language_code else "All"
            )

            needs_fix = 0
            if language_code == "lt" and inferred_pos_type == "noun":
                check_results = agent.check_noun_declension_coverage()
                needs_fix = check_results.get("needs_declensions", 0)
            elif language_code == "fr" and inferred_pos_type == "verb":
                check_results = agent.check_verb_conjugation_coverage(language_code="fr")
                needs_fix = check_results.get("needs_conjugations", 0)
            elif language_code == "lt" and inferred_pos_type == "verb":
                check_results = agent.check_verb_conjugation_coverage(language_code="lt")
                needs_fix = check_results.get("needs_conjugations", 0)

            if not display.print_fix_confirmation(lang_name, form_type_label, needs_fix, args):
                print("Aborted.")
                return

        # For "all" task, we need to process each supported combination
        if args.task == "all":
            print("\n=== Processing all supported forms ===\n")

            # Process all language/POS combinations
            languages_and_pos = []
            for lang in selected_languages:
                for pos in SUPPORTED_TASKS[lang]:
                    languages_and_pos.append((lang, pos))

            # Process each language/POS combination
            task_num = 1
            for lang, pos in languages_and_pos:
                lang_name = LANGUAGE_NAMES.get(lang, lang.upper())

                # Use correct terminology based on language and POS type
                if pos == "noun":
                    # Use "declensions" for case languages (LT, DE), "forms" for others
                    form_desc = "noun declensions" if lang in ["lt", "de"] else "noun forms"
                else:
                    form_desc = {
                        "verb": "verb conjugations",
                        "adjective": "adjective forms",
                        "adverb": "adverb forms",
                    }.get(pos, f"{pos} forms")

                display_language_header(lang, task_num, len(languages_and_pos))
                print(f"{lang_name} {form_desc}:")

                kwargs = {
                    "lemmas": lemmas,
                    "language_code": lang,
                    "pos_type": pos,
                    "limit": args.limit,
                    "model": args.model,
                    "throttle": args.throttle,
                    "dry_run": args.dry_run,
                    "use_wiktionary": args.use_wiktionary,
                }

                results = agent.fix_missing_forms(**kwargs)
                display.print_fix_results(results, args.dry_run)
                task_num += 1

            print("\n=== All forms processed ===")
        else:
            # Single task - language_code should be set by task parsing
            assert language_code is not None, "language_code must be set for single task"
            results = agent.fix_missing_forms(
                lemmas=lemmas,
                language_code=language_code,
                pos_type=inferred_pos_type,
                limit=args.limit,
                model=args.model,
                throttle=args.throttle,
                dry_run=args.dry_run,
                use_wiktionary=args.use_wiktionary,
            )
            display.print_fix_results(results, args.dry_run)

        return

    # Coverage mode - report what needs work
    if mode == "coverage":
        print("\n=== Coverage Report ===\n")

        # Run full check which reports all coverage stats
        results = agent.run_full_check(output_file=args.output)
        return


if __name__ == "__main__":
    main()
