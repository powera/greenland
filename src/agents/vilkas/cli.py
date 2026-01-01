#!/usr/bin/env python3
"""
Vilkas Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys
from pathlib import Path

from src.agents.common.common_args import (
    add_common_args,
    add_llm_args,
    add_output_args,
    add_processing_args,
    add_guid_arg,
    add_language_args,
    add_backend_args,
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


def get_argument_parser():
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

    # Fix mode options (generate missing forms)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix mode: Generate missing word forms. Use --task to specify which forms to fix.",
    )
    parser.add_argument(
        "--source",
        choices=["llm", "wiki"],
        default="llm",
        help="[Fix mode] Source for Lithuanian noun forms: llm (default) or wiki (Wiktionary)",
    )

    return parser


def main():
    """Main entry point for the vilkas agent."""
    # Import here to avoid circular imports
    from agents.vilkas.agent import VilkasAgent
    from agents.vilkas import display

    parser = get_argument_parser()
    args = parser.parse_args()

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

    # Handle --guid mode (filter to single lemma)
    if args.guid:
        from wordfreq.storage.models.schema import Lemma, DerivativeForm

        session = agent.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
            if not lemma:
                print(f"\nError: No lemma found with GUID: {args.guid}")
                sys.exit(1)

            print(f"\nProcessing word forms for: {lemma.lemma_text} (GUID: {args.guid})")
            print(f"POS: {lemma.pos_type}")

            # If task=all, process all supported languages for this lemma's POS type
            if args.task == "all":
                pos_type = lemma.pos_type

                # Find all supported languages for this POS type
                languages_to_process = []
                for lang, pos_types in SUPPORTED_TASKS.items():
                    if pos_type in pos_types:
                        languages_to_process.append(lang)

                print(f"Languages to process: {', '.join(languages_to_process)}")

                if args.fix:
                    print(f"\nGenerating missing forms for this lemma across all languages...")
                    for lang in languages_to_process:
                        lang_name = LANGUAGE_NAMES.get(lang, lang.upper())
                        print(f"\n--- Processing {lang_name} forms ---")

                        kwargs = {
                            "language_code": lang,
                            "pos_type": pos_type,
                            "model": args.model,
                            "throttle": args.throttle,
                            "dry_run": args.dry_run,
                            "guid": args.guid,
                        }
                        if lang == "lt" and pos_type == "noun":
                            kwargs["source"] = args.source

                        results = agent.fix_missing_forms(**kwargs)
                        display.print_fix_results(results, args.dry_run)
                else:
                    # Just show existing forms for all languages
                    for lang in languages_to_process:
                        forms = (
                            session.query(DerivativeForm)
                            .filter(
                                DerivativeForm.lemma_id == lemma.id,
                                DerivativeForm.language_code == lang,
                            )
                            .all()
                        )
                        lang_name = LANGUAGE_NAMES.get(lang, lang.upper())
                        print(f"\n{lang_name} forms ({len(forms)}):")
                        if forms:
                            for form in forms[:20]:
                                base_marker = " [BASE]" if form.is_base_form else ""
                                print(
                                    f"  {form.derivative_form_text} ({form.grammatical_form or 'N/A'}){base_marker}"
                                )
                            if len(forms) > 20:
                                print(f"  ... and {len(forms) - 20} more")
                        else:
                            print("  No forms found")
            else:
                # Single language mode
                language_code = args.task.split("-")[0]
                print(f"Language: {language_code}")

                # Get all derivative forms for this lemma
                forms = (
                    session.query(DerivativeForm)
                    .filter(
                        DerivativeForm.lemma_id == lemma.id,
                        DerivativeForm.language_code == language_code,
                    )
                    .all()
                )

                if forms:
                    print(f"\nExisting forms ({len(forms)}):")
                    for form in forms[:20]:  # Limit display to first 20
                        base_marker = " [BASE]" if form.is_base_form else ""
                        print(
                            f"  {form.derivative_form_text} ({form.grammatical_form or 'N/A'}){base_marker}"
                        )
                    if len(forms) > 20:
                        print(f"  ... and {len(forms) - 20} more")
                else:
                    print("\nNo existing forms found")

                # If in --fix mode, generate missing forms for this lemma
                if args.fix:
                    print(f"\nGenerating missing forms for this lemma...")
                    # Use the lemma's actual POS type
                    pos_type_to_use = lemma.pos_type

                    # Call fix_missing_forms with the GUID parameter to filter to just this lemma
                    results = agent.fix_missing_forms(
                        language_code=language_code,
                        pos_type=pos_type_to_use,
                        model=args.model,
                        throttle=args.throttle,
                        dry_run=args.dry_run,
                        source=args.source,
                        guid=args.guid,
                    )
                    display.print_fix_results(results, args.dry_run)
        finally:
            session.close()
        return

    # Handle bulk processing (no --guid filter)
    if args.fix:

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
                        form_type_label = f"{LANGUAGE_NAMES.get(language_code, language_code)} noun declensions"
                    else:
                        form_type_label = f"{LANGUAGE_NAMES.get(language_code, language_code)} noun forms"
                elif form_category == "verb":
                    inferred_pos_type = "verb"
                    form_type_label = f"{LANGUAGE_NAMES.get(language_code, language_code)} verb conjugations"
                elif form_category == "adjective":
                    inferred_pos_type = "adjective"
                    form_type_label = f"{LANGUAGE_NAMES.get(language_code, language_code)} adjective forms"
                elif form_category == "adverb":
                    inferred_pos_type = "adverb"
                    form_type_label = f"{LANGUAGE_NAMES.get(language_code, language_code)} adverb forms"
        elif args.task == "all":
            language_code = None  # Process all languages
            form_type_label = "all forms (all languages)"

        # Confirmation prompt (unless --yes or --dry-run)
        if not args.yes and not args.dry_run:
            # Get appropriate check results for confirmation
            language_names = {"lt": "Lithuanian", "fr": "French"}
            lang_name = language_names.get(language_code, language_code.upper()) if language_code else "All"

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

            # Process each supported language/POS combination
            task_num = 1
            for lang, pos_types in SUPPORTED_TASKS.items():
                lang_name = LANGUAGE_NAMES.get(lang, lang.upper())
                for pos in pos_types:
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

                    print(f"\n{task_num}. {lang_name} {form_desc}:")

                    # Only pass source for Lithuanian nouns
                    kwargs = {
                        "language_code": lang,
                        "pos_type": pos,
                        "limit": args.limit,
                        "model": args.model,
                        "throttle": args.throttle,
                        "dry_run": args.dry_run,
                    }
                    if lang == "lt" and pos == "noun":
                        kwargs["source"] = args.source

                    results = agent.fix_missing_forms(**kwargs)
                    display.print_fix_results(results, args.dry_run)
                    task_num += 1

            print("\n=== All forms processed ===")
        else:
            # Single task
            results = agent.fix_missing_forms(
                language_code=language_code,
                pos_type=inferred_pos_type,
                limit=args.limit,
                model=args.model,
                throttle=args.throttle,
                dry_run=args.dry_run,
                source=args.source,
            )
            display.print_fix_results(results, args.dry_run)

        return

    # If we get here, user wants to check/report (not fix)
    # This is the equivalent of the old --check mode
    print("\nCheck/Report mode (use --fix to actually generate forms)")
    print("This functionality is not yet implemented in the new CLI.")
    print("Use --guid to check a specific lemma, or --fix to generate forms.")
    sys.exit(1)


if __name__ == "__main__":
    main()
