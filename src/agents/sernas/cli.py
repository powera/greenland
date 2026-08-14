#!/usr/bin/env python3
"""
Šernas Agent - Command Line Interface

This module owns argument parsing, lemma selection, confirmation prompts,
enqueueing, and rendering. The synonym work itself lives in
:mod:`words.synonym_workflow` and :mod:`words.synonym_coverage`.
"""

import argparse
from typing import Any, List, Optional, Sequence

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
from workqueue.task_queue import EnqueueSummary, TaskRequest, TaskType, enqueue_tasks


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
    lemmas: Sequence[Any],
    languages: Sequence[str],
    form_type: Optional[str] = None,
    dry_run: bool = False,
) -> EnqueueSummary:
    """Enqueue synonym generation work items to the queue.

    Args:
        session: Database session
        lemmas: Lemmas to process
        languages: Language codes to process
        form_type: Specific form type or None for all
        dry_run: If True, don't actually enqueue

    Returns:
        The queue's enqueued/skipped summary.
    """
    form_key = form_type or "all"
    requests = [
        TaskRequest(
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
            dedup_key=f"{TaskType.WORDS_SYNONYMS}:{lemma.id}:{language_code}:{form_key}",
            legacy_dedup_key=f"sernas_{lemma.id}_{language_code}_{form_key}",
        )
        for lemma in lemmas
        for language_code in languages
    ]
    return enqueue_tasks(session, requests, dry_run=dry_run)


def _run_coverage(
    agent: Any,
    lemmas: List[Any],
    languages: List[str],
    form_type: Optional[str],
    requested_all_languages: bool,
) -> None:
    """Report which lemmas still need synonyms, per requested language."""
    from agents.sernas.cli_display import (
        display_all_language_coverage,
        display_language_coverage,
    )

    # A single language gets a detailed report; "all" gets one summary; an
    # explicit list of languages gets a detailed report each.
    if requested_all_languages and len(languages) > 1:
        report = agent.check_missing_synonyms(lemmas=lemmas, form_type=form_type)
        if report.error:
            print(f"Error: {report.error}")
            return
        display_all_language_coverage(report)
        return

    for language_code in languages:
        report = agent.check_missing_synonyms(
            lemmas=lemmas, language_code=language_code, form_type=form_type
        )
        if report.error:
            print(f"Error: {report.error}")
            continue
        display_language_coverage(report, language_code)


def _confirm_populate(
    agent: Any,
    lemmas: List[Any],
    language_code: str,
    form_type: Optional[str],
    args: argparse.Namespace,
) -> bool:
    """Show how much work populating this language implies, and ask."""
    report = agent.check_missing_synonyms(
        lemmas=lemmas, language_code=language_code, form_type=form_type
    )
    if report.error:
        print(f"Error checking synonyms: {report.error}")
        return False

    missing_count = len(report.for_language(language_code))

    print(f"\nReady to generate synonyms/alternatives for {language_code}")
    print(f"Lemmas needing forms: {missing_count}")
    print(f"Will process: {min(args.limit, missing_count) if args.limit else missing_count}")
    print(f"Model: {args.model}")
    print(f"Throttle: {args.throttle}s between calls")

    return input("\nContinue? [y/N]: ").lower() in ["y", "yes"]


def main() -> None:
    """Main entry point for the šernas agent."""
    from agents.common.cli_display import display_language_header
    from agents.sernas.cli_display import display_batch_results, display_enqueue_summary
    from storage.translation_helpers import (
        get_tier_1_and_tier_2_languages,
        normalize_llm_language_codes,
    )
    from words.lemma_selection import get_lemmas_for_agent
    from words.synonym_workflow import SynonymWorkflow, clear_synonym_records

    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args
    config = get_data_source_config(args)

    # Create the workflow with config
    agent = SynonymWorkflow(config=config)

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
    languages_to_process = normalize_llm_language_codes(
        args.languages if args.languages else ["en"],
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

    if mode == "coverage":
        _run_coverage(agent, lemmas, languages_to_process, form_type, requested_all_languages)
        return

    # WORKQUEUE MODE: Enqueue work items for barsukas worker
    if args.use_workqueue:
        print("\n" + "=" * 80)
        print("ŠERNAS AGENT - ENQUEUING WORK")
        print("=" * 80)

        session = agent.get_session()
        try:
            enqueued = enqueue_sernas_work(
                session=session,
                lemmas=lemmas,
                languages=languages_to_process,
                form_type=form_type,
                dry_run=args.dry_run,
            )
            display_enqueue_summary(enqueued)
        finally:
            session.close()

        return

    # Populate and regenerate differ only in what they clear first: regenerate
    # forgets the previous scan so every lemma is generated again.
    for lang_index, language_code in enumerate(languages_to_process):
        display_language_header(language_code, lang_index + 1, len(languages_to_process))

        if mode == "regenerate":
            # Confirm before clearing: the scan records are what makes these
            # lemmas look "already done", so dropping them and then skipping
            # the language would leave the data worse than it started.
            if not args.yes and not args.dry_run:
                print(f"\nReady to regenerate synonyms/alternatives for {language_code}")
                print(f"Lemmas to process: {len(lemmas)}")
                print(f"Model: {args.model}")
                print(f"Throttle: {args.throttle}s between calls")

                if input("\nContinue? [y/N]: ").lower() not in ["y", "yes"]:
                    print("Skipping this language.")
                    continue

            if not args.dry_run:
                session = agent.get_session()
                try:
                    clear_synonym_records(session, lemmas, language_code)
                finally:
                    session.close()
        elif not args.yes and not args.dry_run:
            if not _confirm_populate(agent, lemmas, language_code, form_type, args):
                print("Skipping this language.")
                continue

        results = agent.fix_missing_synonyms(
            lemmas=lemmas,
            language_code=language_code,
            form_type=form_type,
            limit=args.limit,
            throttle=args.throttle,
            dry_run=args.dry_run,
        )
        display_batch_results(results, language_code, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
