#!/usr/bin/env python3
"""
Vilkas Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys
from pathlib import Path


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Vilkas - Lithuanian Word Forms Checker Agent"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    # Check mode options (reporting only, no changes)
    parser.add_argument('--check',
                       choices=['base-forms', 'noun-declensions', 'verb-conjugations', 'all'],
                       default='all',
                       help='Which check to run in reporting mode (default: all)')

    # Fix mode options (generate missing forms)
    parser.add_argument('--fix', action='store_true',
                       help='Fix mode: Generate missing word forms (supports Lithuanian nouns, French verbs)')
    parser.add_argument('--language', default='lt',
                       help='Language code for operations (lt=Lithuanian, fr=French, default: lt)')
    parser.add_argument('--pos-type',
                       help='[Fix mode] Part of speech to fix (e.g., noun, verb). If not specified, fixes all supported types.')
    parser.add_argument('--limit', type=int, default=20,
                       help='[Fix mode] Maximum number of lemmas to process (default: 20)')
    parser.add_argument('--model', default='gpt-5-mini',
                       help='[Fix mode] LLM model to use for form generation (default: gpt-5-mini)')
    parser.add_argument('--throttle', type=float, default=1.0,
                       help='[Fix mode] Seconds to wait between API calls (default: 1.0)')
    parser.add_argument('--dry-run', action='store_true',
                       help='[Fix mode] Show what would be fixed WITHOUT making any LLM calls or database changes')
    parser.add_argument('--source', choices=['llm', 'wiki'], default='llm',
                       help='[Fix mode] Source for Lithuanian noun forms: llm (default) or wiki (Wiktionary)')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='[Fix mode] Skip confirmation prompt when fixing')

    return parser


def main():
    """Main entry point for the vilkas agent."""
    # Import here to avoid circular imports
    from wordfreq.agents.vilkas.agent import VilkasAgent
    from wordfreq.agents.vilkas import display

    parser = get_argument_parser()
    args = parser.parse_args()

    agent = VilkasAgent(db_path=args.db_path, debug=args.debug)

    # Handle --fix mode
    if args.fix:
        # Confirmation prompt (unless --yes or --dry-run)
        if not args.yes and not args.dry_run:
            # Determine what we're fixing based on language and pos-type
            language_names = {'lt': 'Lithuanian', 'fr': 'French'}
            lang_name = language_names.get(args.language, args.language.upper())

            # Get appropriate check results based on language and POS type
            if args.language == 'lt' and (not args.pos_type or args.pos_type == 'noun'):
                check_results = agent.check_noun_declension_coverage()
                needs_fix = check_results.get('needs_declensions', 0)
                form_type = 'noun declensions'
            elif args.language == 'fr' and (not args.pos_type or args.pos_type == 'verb'):
                check_results = agent.check_verb_conjugation_coverage(language_code='fr')
                needs_fix = check_results.get('needs_conjugations', 0)
                form_type = 'verb conjugations'
            elif args.language == 'lt' and args.pos_type == 'verb':
                check_results = agent.check_verb_conjugation_coverage(language_code='lt')
                needs_fix = check_results.get('needs_conjugations', 0)
                form_type = 'verb conjugations'
            else:
                needs_fix = 0
                form_type = 'forms'

            if not display.print_fix_confirmation(lang_name, form_type, needs_fix, args):
                print("Aborted.")
                return

        results = agent.fix_missing_forms(
            language_code=args.language,
            pos_type=args.pos_type,
            limit=args.limit,
            model=args.model,
            throttle=args.throttle,
            dry_run=args.dry_run,
            source=args.source
        )

        display.print_fix_results(results, args.dry_run)
        return

    # Handle check mode (existing functionality)
    if args.check == 'base-forms':
        # Only Lithuanian has base forms check currently
        results = agent.check_missing_lithuanian_base_forms()
        display.print_base_forms_check(results)

    elif args.check == 'noun-declensions':
        # Only Lithuanian has noun declensions currently
        results = agent.check_noun_declension_coverage()
        display.print_noun_declensions_check(results)

    elif args.check == 'verb-conjugations':
        # Support both Lithuanian and French verb conjugations
        results = agent.check_verb_conjugation_coverage(language_code=args.language)
        display.print_verb_conjugations_check(results, args.language)

    else:  # all
        agent.run_full_check(output_file=args.output)


if __name__ == '__main__':
    main()
