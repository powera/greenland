#!/usr/bin/env python3
"""
Dramblys Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)


def main():
    """Main entry point for the dramblys agent."""
    # Import here to avoid circular imports
    from wordfreq.agents.dramblys.agent import DramblysAgent

    parser = argparse.ArgumentParser(
        description="Dramblys - Missing Words Detection Agent"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')

    # Check mode options (reporting only, no changes)
    parser.add_argument('--check',
                       choices=['frequency', 'orphaned', 'subtypes', 'levels', 'all'],
                       default='all',
                       help='Which check to run in reporting mode (default: all)')
    parser.add_argument('--top-n', type=int, default=5000,
                       help='Number of top frequency words to check (default: 5000)')
    parser.add_argument('--min-subtype-count', type=int, default=10,
                       help='Minimum expected words per subtype (default: 10)')

    # Fix mode options (process missing words)
    parser.add_argument('--fix', action='store_true',
                       help='Fix mode: Process high-frequency missing words using LLM')
    parser.add_argument('--limit', type=int, default=20,
                       help='[Fix mode] Maximum number of words to process (default: 20)')
    parser.add_argument('--model', default='gpt-5-mini',
                       help='[Fix mode] LLM model to use (default: gpt-5-mini)')
    parser.add_argument('--throttle', type=float, default=1.0,
                       help='[Fix mode] Seconds to wait between API calls (default: 1.0)')
    parser.add_argument('--dry-run', action='store_true',
                       help='[Fix mode] Show what would be fixed WITHOUT making any LLM calls')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='[Fix mode] Skip confirmation prompt')

    # Staging mode options (two-step import workflow)
    parser.add_argument('--stage', action='store_true',
                       help='Stage mode: Add missing words to pending_imports for review')
    parser.add_argument('--target-language', default='lt',
                       help='[Stage mode] Language code for disambiguation translations (default: lt)')

    # Pending imports management
    parser.add_argument('--list-pending', action='store_true',
                       help='List pending imports from staging table')
    parser.add_argument('--approve', type=int, metavar='ID',
                       help='Approve a pending import by ID')
    parser.add_argument('--reject', type=int, metavar='ID',
                       help='Reject a pending import by ID')
    parser.add_argument('--rejection-reason', default='manual_rejection',
                       help='Reason for rejection (default: manual_rejection)')
    parser.add_argument('--no-exclude', action='store_true',
                       help='Do not add rejected word to exclusions list')

    # Subtype mode options
    parser.add_argument('--add-subtype', action='store_true',
                       help='Add words for a specific POS subtype from high-frequency words')
    parser.add_argument('--pos-type', type=str,
                       help='[Subtype mode] Part of speech: noun, verb, adjective, adverb')
    parser.add_argument('--pos-subtype', type=str,
                       help='[Subtype mode] Specific subtype (e.g., animals, physical_action)')
    parser.add_argument('--find-only', action='store_true',
                       help='[Subtype mode] Only find matching words, do not add them')
    parser.add_argument('--stage-only', action='store_true',
                       help='[Subtype mode] Stage to pending_imports instead of processing directly')

    args = parser.parse_args()

    agent = DramblysAgent(db_path=args.db_path, debug=args.debug)

    # Handle --list-pending mode
    if args.list_pending:
        results = agent.list_pending_imports(
            pos_type=args.pos_type,
            pos_subtype=args.pos_subtype,
            limit=args.limit if hasattr(args, 'limit') else None
        )

        if 'error' in results:
            print(f"\nError: {results['error']}")
        else:
            print(f"\n{'='*80}")
            print(f"PENDING IMPORTS: {results['count']} entries")
            print(f"{'='*80}\n")

            for i, pending in enumerate(results['pending_imports'], 1):
                print(f"{i}. ID {pending['id']}: '{pending['english_word']}'")
                print(f"   Definition: {pending['definition'][:80]}...")
                print(f"   Translation ({pending['language']}): {pending['translation']}")
                if pending['pos_type']:
                    print(f"   POS: {pending['pos_type']}/{pending['pos_subtype']}")
                if pending['frequency_rank']:
                    print(f"   Frequency rank: {pending['frequency_rank']}")
                print(f"   Source: {pending['source']}")
                print()

            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                print(f"Full results written to: {args.output}")
        return

    # Handle --approve mode
    if args.approve:
        results = agent.approve_pending_import(args.approve, model=args.model)

        if results['success']:
            print(f"\nSuccess: {results['message']}")
        else:
            print(f"\nError: {results.get('error', 'Unknown error')}")
        return

    # Handle --reject mode
    if args.reject:
        results = agent.reject_pending_import(
            args.reject,
            reason=args.rejection_reason,
            add_to_exclusions=not args.no_exclude
        )

        if results['success']:
            print(f"\nSuccess: {results['message']}")
            if results['added_to_exclusions']:
                print(f"  Added '{results['word']}' to exclusions")
        else:
            print(f"\nError: {results.get('error', 'Unknown error')}")
        return

    # Handle --stage mode
    if args.stage:
        if not args.yes and not args.dry_run:
            check_results = agent.check_high_frequency_missing_words(top_n=args.top_n)
            total_missing = check_results.get('missing_count', 0)

            print(f"\n{'='*60}")
            print(f"Ready to stage high-frequency missing words")
            print(f"Total missing words found: {total_missing}")
            if args.limit:
                print(f"Limit: {args.limit} words")
            print(f"Model: {args.model}")
            print(f"Target language: {args.target_language}")
            print(f"Throttle: {args.throttle}s between calls")
            print(f"\nWords will be added to pending_imports for review")
            print(f"{'='*60}")
            response = input("\nContinue? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Aborted.")
                return

        results = agent.stage_missing_words_for_import(
            top_n=args.top_n,
            limit=args.limit,
            model=args.model,
            throttle=args.throttle,
            dry_run=args.dry_run,
            target_language=args.target_language
        )

        if 'error' in results:
            print(f"\nError: {results['error']}")
        else:
            if args.dry_run:
                print(f"\nDRY RUN: Would stage {results['would_stage']} words out of {results['total_missing']} total")
            else:
                print(f"\nStaging complete:")
                print(f"  Total missing: {results['total_missing']}")
                print(f"  Processed: {results['processed']}")
                print(f"  Staged: {results['staged']}")
                print(f"  Skipped (already pending): {results['skipped_already_pending']}")
                print(f"  Failed: {results['failed']}")
                print(f"\nUse --list-pending to review staged words")
        return

    # Handle --add-subtype mode
    if args.add_subtype:
        if not args.pos_type or not args.pos_subtype:
            print("Error: --add-subtype requires --pos-type and --pos-subtype")
            return

        if args.find_only:
            # Just find and display
            results = agent.find_words_for_subtype(
                pos_type=args.pos_type,
                pos_subtype=args.pos_subtype,
                top_n=args.top_n,
                model=args.model
            )

            if 'error' in results:
                print(f"\nError: {results['error']}")
            else:
                print(f"\n{'='*80}")
                print(f"FOUND {results['matches_found']} {args.pos_type.upper()} WORDS FOR SUBTYPE: {args.pos_subtype}")
                print(f"Reviewed top {results['total_words_reviewed']} frequency words")
                print(f"{'='*80}\n")

                for i, match in enumerate(results['matches'], 1):
                    print(f"{i}. '{match['word']}' - {match['definition']}")
                    print(f"   Confidence: {match.get('confidence', 'N/A')}\n")

                # Write to output file if requested
                if args.output:
                    with open(args.output, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    print(f"Full results written to: {args.output}")
        else:
            # Find and add
            if not args.yes and not args.dry_run:
                # Preview first
                preview = agent.find_words_for_subtype(
                    pos_type=args.pos_type,
                    pos_subtype=args.pos_subtype,
                    top_n=args.top_n,
                    model=args.model
                )

                if 'error' in preview:
                    print(f"\nError: {preview['error']}")
                    return

                print(f"\n{'='*60}")
                print(f"Found {preview['matches_found']} {args.pos_type} words for subtype '{args.pos_subtype}'")
                print(f"Model: {args.model}")
                print(f"Throttle: {args.throttle}s between calls")
                print(f"\nSample words:")
                for match in preview['matches'][:5]:
                    print(f"  - '{match['word']}': {match['definition'][:60]}...")
                print(f"{'='*60}")
                response = input("\nContinue to add these words? [y/N]: ")
                if response.lower() not in ['y', 'yes']:
                    print("Aborted.")
                    return

            results = agent.add_words_for_subtype(
                pos_type=args.pos_type,
                pos_subtype=args.pos_subtype,
                top_n=args.top_n,
                model=args.model,
                throttle=args.throttle,
                dry_run=args.dry_run,
                stage_only=args.stage_only,
                target_language=args.target_language
            )

            if 'error' in results:
                print(f"\nError: {results['error']}")
            else:
                if args.dry_run:
                    action = "stage" if args.stage_only else "add"
                    print(f"\nDRY RUN: Would {action} {results['would_add']} words")
                else:
                    print(f"\nComplete:")
                    print(f"  Matches found: {results['matches_found']}")
                    if args.stage_only:
                        print(f"  Staged: {results['staged']}")
                        print(f"\nUse --list-pending to review staged words")
                    else:
                        print(f"  Successfully added: {results['successful']}")
                    print(f"  Failed: {results['failed']}")
                    print(f"  Skipped (already exist): {results['skipped']}")
        return

    # Handle --fix mode
    if args.fix:
        # Confirmation prompt (unless --yes or --dry-run)
        if not args.yes and not args.dry_run:
            check_results = agent.check_high_frequency_missing_words(top_n=args.top_n)
            total_missing = check_results.get('missing_count', 0)

            print(f"\n{'='*60}")
            print(f"Ready to process high-frequency missing words using LLM")
            print(f"Total missing words found: {total_missing}")
            if args.limit:
                print(f"Limit: {args.limit} words")
            print(f"Model: {args.model}")
            print(f"Throttle: {args.throttle}s between calls")
            print(f"\nThis will:")
            print(f"  - Query LLM for definitions, lemmas, and POS info")
            print(f"  - Handle plurals, polysemous words, and grammatical words")
            print(f"  - Create multiple lemmas for words with multiple meanings")
            print(f"  - Correctly identify base forms vs. inflected forms")
            print(f"{'='*60}")
            response = input("\nContinue? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Aborted.")
                return

        results = agent.fix_missing_words(
            top_n=args.top_n,
            limit=args.limit,
            model=args.model,
            throttle=args.throttle,
            dry_run=args.dry_run
        )

        if 'error' in results:
            print(f"\nError: {results['error']}")
        else:
            if args.dry_run:
                print(f"\nDRY RUN: Would process {results['would_process']} words out of {results['total_missing']} total")
            else:
                print(f"\nFix complete:")
                print(f"  Total missing: {results['total_missing']}")
                print(f"  Processed: {results['processed']}")
                print(f"  Successful: {results['successful']}")
                print(f"  Failed: {results['failed']}")
        return

    # Handle check mode (existing functionality)
    if args.check == 'frequency':
        results = agent.check_high_frequency_missing_words(top_n=args.top_n)
        agent._print_frequency_check(results, max_words=200)

        # Write to output file if requested
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Full results written to: {args.output}")

    elif args.check == 'orphaned':
        results = agent.check_orphaned_derivative_forms()
        print(f"\nOrphaned derivative forms: {results['orphaned_count']} out of {results['total_forms_checked']}")

    elif args.check == 'subtypes':
        results = agent.check_subtype_coverage(min_expected=args.min_subtype_count)
        print(f"\nUnder-covered subtypes: {results['under_covered_count']} out of {results['total_subtypes']}")

    elif args.check == 'levels':
        results = agent.check_difficulty_level_distribution()
        print(f"\nEmpty difficulty levels: {len(results['gaps'])}")
        print(f"Imbalanced levels: {len(results['imbalanced'])}")

    else:  # all
        agent.run_full_check(
            output_file=args.output,
            top_n_frequency=args.top_n,
            min_subtype_count=args.min_subtype_count
        )


if __name__ == '__main__':
    main()
