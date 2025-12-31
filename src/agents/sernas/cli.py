#!/usr/bin/env python3
"""
Šernas Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys

from agents.common_args import (
    add_common_args,
    add_llm_args,
    add_processing_args,
    add_guid_arg,
    add_language_args,
    add_backend_args,
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
    add_language_args(parser, multiple=False)
    add_backend_args(parser)

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

    # Override default language to 'en'
    parser.set_defaults(language="en", limit=10)

    return parser


def main():
    """Main entry point for the šernas agent."""
    # Import here to avoid circular imports
    from agents.sernas.agent import SernasAgent

    parser = get_argument_parser()
    args = parser.parse_args()

    # Create configuration from args (always returns a valid config with defaults)
    config = get_data_source_config(args)

    # Create agent with config
    agent = SernasAgent(config=config)

    # Handle --guid mode (single lemma)
    if args.guid:
        from wordfreq.storage.models.schema import Lemma
        from wordfreq.storage.crud.grammar_fact import get_alternate_forms_facts
        from wordfreq.storage.translation_helpers import get_translation

        session = agent.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
            if not lemma:
                print(f"\nError: No lemma found with GUID: {args.guid}")
                sys.exit(1)

            # Get the word in the target language
            if args.language == "en":
                word = lemma.lemma_text
            else:
                word = get_translation(session, lemma, args.language)

            if not word or not word.strip():
                print(f"\nError: No {args.language} translation found for GUID: {args.guid}")
                print(f"English lemma: {lemma.lemma_text}")
                sys.exit(1)

            print(f"\nProcessing synonyms/alternatives for: {word} ({args.language})")
            print(f"English lemma: {lemma.lemma_text}")
            print(f"POS: {lemma.pos_type}")
            print(f"GUID: {args.guid}")

            # Get existing alternative forms
            existing_forms = get_alternate_forms_facts(session, lemma.id, args.language)
            if existing_forms:
                print(f"\nExisting alternative forms ({len(existing_forms)}):")
                for form_type, forms in existing_forms.items():
                    if forms:
                        print(f"  {form_type}: {', '.join(forms)}")
            else:
                print("\nNo existing alternative forms found")

            # If in --fix mode, generate synonyms
            if args.fix:
                print(f"\nGenerating synonyms and alternative forms...")
                result = agent.generate_synonyms_for_lemma(
                    lemma_id=lemma.id,
                    language_code=args.language,
                    model=args.model,
                    dry_run=args.dry_run,
                )

                if "error" in result:
                    print(f"\nError: {result['error']}")
                elif result.get("dry_run"):
                    print("\n[DRY RUN] Would generate:")
                    if result.get("synonyms"):
                        print(f"  Synonyms: {', '.join(result['synonyms'])}")
                    if result.get("abbreviations"):
                        print(f"  Abbreviations: {', '.join(result['abbreviations'])}")
                    if result.get("expanded_forms"):
                        print(f"  Expanded forms: {', '.join(result['expanded_forms'])}")
                    if result.get("alternate_spellings"):
                        print(f"  Alternate spellings: {', '.join(result['alternate_spellings'])}")
                else:
                    print("\n✓ Generated and saved:")
                    if result.get("synonyms"):
                        print(f"  Synonyms: {', '.join(result['synonyms'])}")
                    if result.get("abbreviations"):
                        print(f"  Abbreviations: {', '.join(result['abbreviations'])}")
                    if result.get("expanded_forms"):
                        print(f"  Expanded forms: {', '.join(result['expanded_forms'])}")
                    if result.get("alternate_spellings"):
                        print(f"  Alternate spellings: {', '.join(result['alternate_spellings'])}")
        finally:
            session.close()
        return

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
