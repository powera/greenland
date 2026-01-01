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
        from wordfreq.storage.crud.grammar_fact import get_alternate_forms_facts, delete_grammar_fact
        from wordfreq.storage.translation_helpers import get_translation, get_supported_languages
        import time

        session = agent.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
            if not lemma:
                print(f"\nError: No lemma found with GUID: {args.guid}")
                sys.exit(1)

            print(f"\nProcessing lemma: {lemma.lemma_text}")
            print(f"POS: {lemma.pos_type}")
            print(f"GUID: {args.guid}")
            print(f"Mode: {args.mode}")

            # Handle "all" as a special language code
            languages_to_process = args.languages
            if "all" in languages_to_process:
                languages_to_process = ["en"] + list(get_supported_languages().keys())
                print(f"Processing all languages: {', '.join(languages_to_process)}")

            # Process each language
            for lang_idx, language_code in enumerate(languages_to_process):
                print(f"\n{'='*60}")
                print(f"Language [{lang_idx + 1}/{len(languages_to_process)}]: {language_code.upper()}")
                print(f"{'='*60}")

                # Get the word in the target language
                if language_code == "en":
                    word = lemma.lemma_text
                else:
                    word = get_translation(session, lemma, language_code)

                if not word or not word.strip():
                    print(f"⚠ No translation found for {language_code}, skipping...")
                    continue

                print(f"Word: {word}")

                # Get existing alternative forms facts
                existing_forms = get_alternate_forms_facts(session, lemma.id, language_code)

                if existing_forms:
                    print(f"\nExisting grammar facts:")
                    for fact_type, value in existing_forms.items():
                        print(f"  {fact_type}: {value}")
                else:
                    print("\nNo existing grammar facts (not yet processed)")

                # Decide whether to process based on mode
                should_process = False

                if args.mode == "coverage":
                    # Just report, don't generate
                    print("\n[coverage mode] Skipping generation")
                    should_process = False

                elif args.mode == "populate-only":
                    # Only process if no facts exist yet
                    if existing_forms is None:
                        print("\n[populate-only mode] No facts exist, will generate")
                        should_process = True
                    else:
                        print("\n[populate-only mode] Facts already exist, skipping")
                        should_process = False

                elif args.mode == "regenerate":
                    # Always process, delete old facts first
                    print("\n[regenerate mode] Will delete old facts and regenerate")
                    should_process = True
                    # Delete old grammar facts
                    if existing_forms:
                        delete_grammar_fact(session, lemma.id, language_code, "has_synonyms")
                        delete_grammar_fact(session, lemma.id, language_code, "has_abbreviations")
                        delete_grammar_fact(session, lemma.id, language_code, "has_expanded_forms")
                        delete_grammar_fact(session, lemma.id, language_code, "has_alternate_spellings")
                        session.commit()

                if should_process:
                    print(f"\nGenerating synonyms and alternative forms...")
                    result = agent.generate_synonyms_for_lemma(
                        lemma_id=lemma.id,
                        language_code=language_code,
                        model=args.model,
                        dry_run=args.dry_run,
                    )

                    if "error" in result:
                        print(f"\n✗ Error: {result['error']}")
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

                    # Throttle between languages (except for the last one)
                    if lang_idx < len(languages_to_process) - 1:
                        time.sleep(args.throttle)

        finally:
            session.close()
        return

    # Convert --type argument to form_type
    form_type = None
    if args.type and args.type != "all":
        form_type = args.type

    # Get languages to process
    from wordfreq.storage.translation_helpers import get_supported_languages
    languages_to_process = args.languages if args.languages else ["en"]
    if "all" in languages_to_process:
        languages_to_process = ["en"] + list(get_supported_languages().keys())

    # Handle populate-only mode (or legacy --fix)
    if args.mode == "populate-only":
        # Process each language
        for lang_idx, language_code in enumerate(languages_to_process):
            print(f"\n{'='*60}")
            print(f"Processing language [{lang_idx + 1}/{len(languages_to_process)}]: {language_code.upper()}")
            print(f"{'='*60}")

            # Confirmation prompt (unless --yes or --dry-run)
            if not args.yes and not args.dry_run:
                # Get check results to show how many need fixing
                check_results = agent.check_missing_synonyms(
                    language_code=language_code, form_type=form_type
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
                language_code=language_code,
                form_type=form_type,
                limit=args.limit,
                model=args.model,
                throttle=args.throttle,
                dry_run=args.dry_run,
            )

            # Print results
            print(f"\n{'='*60}")
            if args.dry_run:
                print(f"DRY RUN COMPLETE - {language_code.upper()}")
                print(f"Would process: {results.get('would_process', 0)} lemmas")
            else:
                print(f"FIX COMPLETE - {language_code.upper()}")
                print(f"Total needing fix: {results.get('total_needing_fix', 0)}")
                print(f"Processed: {results.get('processed', 0)}")
                print(f"Successful: {results.get('successful', 0)}")
                print(f"Failed: {results.get('failed', 0)}")
            print(f"{'='*60}")
        return

    # Handle coverage mode (report missing synonyms)
    if args.mode == "coverage":
        # Check specific languages or all languages
        if len(languages_to_process) == 1 or "all" in args.languages:
            # Single language or all languages - use simpler report
            results = agent.check_missing_synonyms(
                language_code=languages_to_process[0] if len(languages_to_process) == 1 else None,
                form_type=form_type
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
                        print(f"  {i}. {lemma['english']} -> {lemma['translation']} ({lemma['pos_type']})")
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
                results = agent.check_missing_synonyms(language_code=language_code, form_type=form_type)

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
                        print(f"  {i}. {lemma['english']} -> {lemma['translation']} ({lemma['pos_type']})")
                    if len(missing) > 10:
                        print(f"  ... and {len(missing) - 10} more")

                print(f"{'='*60}")


if __name__ == "__main__":
    main()
