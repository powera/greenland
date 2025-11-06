#!/usr/bin/env python3
"""
Voras Agent - Command Line Interface

This module handles all CLI argument parsing and the main entry point.
"""

import argparse
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

# Language mappings for CLI
LANGUAGE_FIELDS = {
    'lt': ('lithuanian_translation', 'Lithuanian'),
    'zh': ('chinese_translation', 'Chinese'),
    'ko': ('korean_translation', 'Korean'),
    'fr': ('french_translation', 'French'),
    'es': ('spanish_translation', 'Spanish'),
    'de': ('german_translation', 'German'),
    'pt': ('portuguese_translation', 'Portuguese'),
    'sw': ('swahili_translation', 'Swahili'),
    'vi': ('vietnamese_translation', 'Vietnamese')
}


def main():
    """Main entry point for the voras agent."""
    # Import here to avoid circular imports
    from wordfreq.agents.voras.agent import VorasAgent
    from wordfreq.storage.models.schema import Lemma

    parser = argparse.ArgumentParser(
        description="Voras - Multi-lingual Translation Validator and Populator"
    )
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--mode',
                       choices=['check-only', 'populate-only', 'both', 'coverage', 'regenerate'],
                       default='coverage',
                       help='Operation mode: check-only (validate existing), populate-only (add missing), both (validate + populate), coverage (report only, default), regenerate (delete and regenerate, supports --batch)')
    parser.add_argument('--language',
                       choices=list(LANGUAGE_FIELDS.keys()),
                       help='Specific language to process (lt, zh, ko, fr, sw, vi)')
    parser.add_argument('--yes', '-y', action='store_true',
                       help='Skip confirmation prompt before running LLM queries')
    parser.add_argument('--model', default='gpt-5-mini',
                       help='LLM model to use (default: gpt-5-mini)')
    parser.add_argument('--limit', type=int,
                       help='Maximum items to process per language')
    parser.add_argument('--sample-rate', type=float, default=1.0,
                       help='Fraction of items to sample for validation (0.0-1.0, default: 1.0)')
    parser.add_argument('--confidence-threshold', type=float, default=0.7,
                       help='Minimum confidence to flag issues (0.0-1.0, default: 0.7)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--batch', action='store_true',
                       help='Use batch mode (supported by --mode regenerate only): queue requests instead of making synchronous API calls')
    parser.add_argument('--batch-submit', action='store_true',
                       help='Submit all pending batch requests to OpenAI')
    parser.add_argument('--batch-status', type=str, metavar='BATCH_ID',
                       help='Check status of a submitted batch (requires only batch ID)')
    parser.add_argument('--batch-retrieve', type=str, metavar='BATCH_ID',
                       help='Retrieve and process results from a completed batch (requires only batch ID)')

    args = parser.parse_args()

    # Create agent with model parameter
    agent = VorasAgent(db_path=args.db_path, debug=args.debug, model=args.model)

    # Handle batch operations first (special cases)
    if args.batch_submit:
        agent.submit_batch()
        return

    if args.batch_status:
        agent.check_batch_status(args.batch_status)
        return

    if args.batch_retrieve:
        agent.retrieve_batch_results(args.batch_retrieve)
        return

    # Handle regenerate mode (special case)
    if args.mode == 'regenerate':
        # Estimate LLM calls for regeneration
        if not args.yes and not args.dry_run:
            session = agent.get_session()
            try:
                query = session.query(Lemma).filter(Lemma.guid.isnot(None))
                if args.limit:
                    query = query.limit(args.limit)
                word_count = query.count()

                print(f"\nREGENERATION MODE")
                print(f"This will:")
                print(f"  1. Delete all non-Lithuanian translations")
                if args.batch:
                    print(f"  2. Queue {word_count} batch requests (1 per word) for later submission")
                    print(f"\nModel: {args.model}")
                    print(f"Words to process: {word_count}")
                    print(f"\nBatch mode: Requests will be queued locally, then submitted with --batch-submit")
                else:
                    print(f"  2. Regenerate them fresh using {word_count} LLM API calls (1 per word)")
                    print(f"\nModel: {args.model}")
                    print(f"Words to process: {word_count}")
                    print("\nThis may incur costs and take some time to complete.")
                response = input("Do you want to proceed? [y/N]: ").strip().lower()

                if response not in ['y', 'yes']:
                    print("Aborted.")
                    sys.exit(0)
                print()
            finally:
                session.close()

        # Execute regeneration
        results = agent.regenerate_all_translations(
            limit=args.limit,
            dry_run=args.dry_run,
            batch_mode=args.batch
        )

        # Print summary
        print("\n" + "=" * 80)
        if args.batch:
            print("BATCH QUEUE COMPLETE")
            print("=" * 80)
            print(f"Words processed: {results['total_words_processed']}")
            print(f"Batch requests queued: {results.get('batch_requests_queued', 0)}")
            print()
            print("Next steps:")
            print(f"  1. Submit batch: python -m wordfreq.agents.voras --batch-submit")
            print(f"  2. Check status: python -m wordfreq.agents.voras --batch-status <batch_id>")
            print(f"  3. Retrieve results: python -m wordfreq.agents.voras --batch-retrieve <batch_id>")
        else:
            print("REGENERATION COMPLETE")
            print("=" * 80)
            print(f"Words processed: {results['total_words_processed']}")
            print(f"Total translations added: {results['total_translations_added']}")
            print(f"Total failed: {results['total_failed']}")
            print()
            for lang_code, lang_results in results['by_language'].items():
                print(f"{lang_results['language_name']}:")
                print(f"  Deleted: {lang_results['deleted']}")
                print(f"  Added: {lang_results['added']}")
                print(f"  Failed: {lang_results['failed']}")
        print("=" * 80)
        return

    # Handle different modes
    if args.mode == 'coverage':
        # Coverage reporting mode (no LLM calls)
        agent.run_full_check(output_file=args.output)
        return

    # For modes requiring LLM, confirm before running (unless --yes was provided)
    if not args.yes and not args.dry_run:
        import logging
        logger = logging.getLogger(__name__)

        session = agent.get_session()
        try:
            estimated_calls = 0
            languages_to_process = [args.language] if args.language else list(LANGUAGE_FIELDS.keys())

            if args.mode in ['check-only', 'both']:
                # Calculate validation calls
                if args.language:
                    # Single language: still validates all languages per word, just filters which words
                    field_name, language_name = LANGUAGE_FIELDS[args.language]
                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None),
                        getattr(Lemma, field_name).isnot(None),
                        getattr(Lemma, field_name) != ''
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    count = query.count()
                    if args.sample_rate < 1.0:
                        count = int(count * args.sample_rate)
                    estimated_calls += count
                    logger.info(f"{language_name}: {count} words to validate (all translations per word)")
                else:
                    # All languages: one call per word with any translation
                    has_translation_filter = None
                    for lang_code, (field_name, _) in LANGUAGE_FIELDS.items():
                        field_filter = (
                            (getattr(Lemma, field_name).isnot(None)) &
                            (getattr(Lemma, field_name) != '')
                        )
                        if has_translation_filter is None:
                            has_translation_filter = field_filter
                        else:
                            has_translation_filter = has_translation_filter | field_filter

                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None),
                        has_translation_filter
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    count = query.count()
                    if args.sample_rate < 1.0:
                        count = int(count * args.sample_rate)
                    estimated_calls += count
                    logger.info(f"All languages: {count} words to validate (all translations per word)")

            if args.mode in ['populate-only', 'both']:
                # Calculate population calls - one call per word with any missing translation
                missing_filter = None
                for lang_code in languages_to_process:
                    field_name, language_name = LANGUAGE_FIELDS[lang_code]
                    lang_filter = (
                        (getattr(Lemma, field_name).is_(None)) |
                        (getattr(Lemma, field_name) == '')
                    )
                    if missing_filter is None:
                        missing_filter = lang_filter
                    else:
                        missing_filter = missing_filter | lang_filter

                query = session.query(Lemma).filter(
                    Lemma.guid.isnot(None),
                    missing_filter
                )
                if args.limit:
                    query = query.limit(args.limit)

                words_to_populate = query.all()
                count = len(words_to_populate)
                estimated_calls += count

                # Count missing per language for reporting
                for lang_code in languages_to_process:
                    field_name, language_name = LANGUAGE_FIELDS[lang_code]
                    missing_count = sum(
                        1 for lemma in words_to_populate
                        if not getattr(lemma, field_name) or not getattr(lemma, field_name).strip()
                    )
                    logger.info(f"{language_name}: {missing_count} missing translations to populate")

                logger.info(f"Total: {count} words to populate (1 LLM call per word for all missing translations)")

        finally:
            session.close()

        print(f"\nThis will make approximately {estimated_calls} LLM API calls using model '{args.model}'.")
        print("This may incur costs and take some time to complete.")
        response = input("Do you want to proceed? [y/N]: ").strip().lower()

        if response not in ['y', 'yes']:
            print("Aborted.")
            sys.exit(0)

        print()  # Extra newline for readability

    # Execute the requested mode
    results = {}

    if args.mode == 'check-only':
        # Validate existing translations
        if args.language:
            results = agent.validate_translations(
                args.language,
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
            print(f"\n{results['language_name']} validation results:")
            print(f"  Issues found: {results['issues_found']} out of {results['total_checked']}")
            print(f"  Issue rate: {results['issue_rate']:.1f}%")
        else:
            results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
            print(f"\nTotal translation issues (all languages): {results['total_issues_all_languages']}")

    elif args.mode == 'populate-only':
        # Generate missing translations only
        results = agent.fix_missing_translations(
            language_code=args.language,
            limit=args.limit,
            dry_run=args.dry_run
        )
        print("\n" + "=" * 80)
        print("TRANSLATION POPULATION SUMMARY")
        print("=" * 80)
        for lang_code, lang_results in results['by_language'].items():
            print(f"\n{lang_results['language_name']}:")
            print(f"  Total missing: {lang_results['total_missing']}")
            print(f"  Populated: {lang_results['fixed']}")
            print(f"  Failed: {lang_results['failed']}")
        print(f"\nTotal populated: {results['total_fixed']}")
        print(f"Total failed: {results['total_failed']}")
        print("=" * 80)

    elif args.mode == 'both':
        # First validate existing translations
        print("\n=== STEP 1: Validating Existing Translations ===\n")
        if args.language:
            validation_results = agent.validate_translations(
                args.language,
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )
        else:
            validation_results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold
            )

        # Then populate missing translations
        print("\n=== STEP 2: Populating Missing Translations ===\n")
        population_results = agent.fix_missing_translations(
            language_code=args.language,
            limit=args.limit,
            dry_run=args.dry_run
        )

        # Combined summary
        print("\n" + "=" * 80)
        print("COMBINED VALIDATION + POPULATION SUMMARY")
        print("=" * 80)

        if args.language:
            print(f"\nValidation ({validation_results['language_name']}):")
            print(f"  Issues found: {validation_results['issues_found']} out of {validation_results['total_checked']}")
            print(f"  Issue rate: {validation_results['issue_rate']:.1f}%")
        else:
            print(f"\nValidation (all languages):")
            print(f"  Total issues: {validation_results['total_issues_all_languages']}")

        print(f"\nPopulation:")
        for lang_code, lang_results in population_results['by_language'].items():
            print(f"  {lang_results['language_name']}: {lang_results['fixed']} populated, {lang_results['failed']} failed")
        print("=" * 80)


if __name__ == '__main__':
    main()
