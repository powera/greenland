#!/usr/bin/env python3
"""
Šernas Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_llm_args,
    add_processing_args,
    get_data_source_config,
)


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Šernas - Synonym and Alternative Form Generator Agent"
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_language_args(parser, multiple=True)
    add_backend_args(parser)

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["coverage", "populate-only", "regenerate"],
        default="coverage",
        help="Operation mode: coverage (report missing, default), populate-only (add missing only), regenerate (delete and regenerate all)",
    )
    parser.add_argument(
        "--type",
        choices=[
            "synonym",
            "abbreviation",
            "expanded_form",
            "alternate_spelling",
            "alternative_form",
            "all",
        ],
        help="[Check/Fix mode] Type to check/generate. Options: synonym, abbreviation, expanded_form, alternate_spelling, alternative_form (legacy), or all. Default: all",
    )

    # Override default languages to ['en']
    parser.set_defaults(languages=["en"], limit=10)

    return parser


def main():
    """Main entry point for the šernas agent."""
    from agents.common.cli_display import display_language_header
    from agents.common.lemma_selection import get_lemmas_for_agent
    from agents.sernas.agent import SernasAgent
    from agents.sernas.cli_display import display_batch_results
    from wordfreq.storage.translation_helpers import get_supported_languages

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
    languages_to_process = args.languages if args.languages else ["en"]
    if "all" in languages_to_process:
        languages_to_process = ["en"] + list(get_supported_languages().keys())

    # Handle coverage mode (report missing synonyms)
    if args.mode == "coverage":
        # Check specific languages or all languages
        if len(languages_to_process) == 1 or "all" in args.languages:
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

    # Handle populate-only mode
    if args.mode == "populate-only":
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

    # Handle regenerate mode (similar to populate-only but forces regeneration)
    if args.mode == "regenerate":
        from wordfreq.storage.crud.grammar_fact import delete_grammar_fact

        # Process each language
        for lang_idx, language_code in enumerate(languages_to_process):
            display_language_header(language_code, lang_idx + 1, len(languages_to_process))

            # Delete existing grammar facts for all lemmas
            session = agent.get_session()
            try:
                for lemma in lemmas:
                    delete_grammar_fact(session, lemma.id, language_code, "has_synonyms")
                    delete_grammar_fact(session, lemma.id, language_code, "has_abbreviations")
                    delete_grammar_fact(session, lemma.id, language_code, "has_expanded_forms")
                    delete_grammar_fact(session, lemma.id, language_code, "has_alternate_spellings")
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
