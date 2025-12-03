#!/usr/bin/env python3
"""
Šernas Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Šernas - Synonym and Alternative Form Generator Agent"
    )
    parser.add_argument("--db-path", help="Database path (uses default if not specified)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # Check mode options (reporting only, no changes)
    parser.add_argument(
        "--check",
        choices=["all", "by-language"],
        default="all",
        help="Check which lemmas are missing synonyms/alternatives (default: all)",
    )

    # Fix mode options (generate missing synonyms)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix mode: Generate missing synonyms and alternative forms",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language code for operations (en=English, lt=Lithuanian, etc., default: en)",
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
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="[Fix mode] Maximum number of lemmas to process (default: 10)",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="[Fix mode] LLM model to use for generation (default: gpt-5-mini)",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=1.0,
        help="[Fix mode] Seconds to wait between API calls (default: 1.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="[Fix mode] Show what would be generated WITHOUT making any LLM calls or database changes",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="[Fix mode] Skip confirmation prompt when fixing"
    )

    return parser


def main():
    """Main entry point for the šernas agent."""
    # Import here to avoid circular imports
    from agents.sernas.agent import SernasAgent

    parser = get_argument_parser()
    args = parser.parse_args()

    agent = SernasAgent(db_path=args.db_path, debug=args.debug)

    # Convert --type argument to form_type
    form_type = None
    if args.type and args.type != "all":
        form_type = args.type

    # Handle --fix mode
    if args.fix:
        # Confirmation prompt (unless --yes or --dry-run)
        if not args.yes and not args.dry_run:
            # Get check results to show how many need fixing
            check_results = agent.check_missing_synonyms(
                language_code=args.language, form_type=form_type
            )

            if "error" in check_results:
                print(f"Error checking synonyms: {check_results['error']}")
                return

            missing_count = len(check_results["missing_by_language"].get(args.language, []))

            print(f"\n{'='*60}")
            print(f"Ready to generate synonyms/alternatives for {args.language}")
            print(f"Lemmas needing forms: {missing_count}")
            print(
                f"Will process: {min(args.limit, missing_count) if args.limit else missing_count}"
            )
            print(f"Model: {args.model}")
            print(f"Throttle: {args.throttle}s between calls")
            print(f"{'='*60}")

            response = input("\nContinue? [y/N]: ")
            if response.lower() not in ["y", "yes"]:
                print("Aborted.")
                return

        results = agent.fix_missing_synonyms(
            language_code=args.language,
            form_type=form_type,
            limit=args.limit,
            model=args.model,
            throttle=args.throttle,
            dry_run=args.dry_run,
        )

        # Print results
        print(f"\n{'='*60}")
        if args.dry_run:
            print("DRY RUN COMPLETE")
            print(f"Would process: {results.get('would_process', 0)} lemmas")
        else:
            print("FIX COMPLETE")
            print(f"Total needing fix: {results.get('total_needing_fix', 0)}")
            print(f"Processed: {results.get('processed', 0)}")
            print(f"Successful: {results.get('successful', 0)}")
            print(f"Failed: {results.get('failed', 0)}")
        print(f"{'='*60}")
        return

    # Handle check mode
    if args.check == "all":
        results = agent.check_missing_synonyms(form_type=form_type)

        if "error" in results:
            print(f"Error: {results['error']}")
            return

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

    elif args.check == "by-language":
        results = agent.check_missing_synonyms(language_code=args.language, form_type=form_type)

        if "error" in results:
            print(f"Error: {results['error']}")
            return

        missing = results["missing_by_language"].get(args.language, [])

        print(f"\n{'='*60}")
        print(f"ŠERNAS AGENT REPORT - {args.language.upper()}")
        print(f"{'='*60}")
        print(f"Lemmas missing forms: {len(missing)}")
        print(f"Checked form types: {', '.join(results['checked_form_types'])}")
        print("")

        if missing:
            print("Sample lemmas needing forms:")
            for i, lemma in enumerate(missing[:10], 1):
                print(f"  {i}. {lemma['english']} -> {lemma['translation']} ({lemma['pos_type']})")
            if len(missing) > 10:
                print(f"  ... and {len(missing) - 10} more")

        print(f"{'='*60}")


if __name__ == "__main__":
    main()
