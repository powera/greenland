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

from agents.common_args import (
    add_common_args,
    add_llm_args,
    add_output_args,
    add_processing_args,
    add_guid_arg,
    add_backend_args,
    get_data_source_config,
    validate_cache_args,
)

# Import language mappings from translation_helpers (single source of truth)
from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS


def get_argument_parser():
    """Return the argument parser for introspection.

    This function allows external tools to introspect the available
    command-line arguments without executing the main function.
    """
    parser = argparse.ArgumentParser(
        description="Voras - Multi-lingual Translation Validator and Populator"
    )

    # Common arguments
    add_common_args(parser)
    add_llm_args(parser, default_model="gpt-5-mini")
    add_output_args(parser)
    add_processing_args(parser)
    add_guid_arg(parser, help_text="Process only the lemma with this GUID")
    add_backend_args(parser)

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["check-only", "populate-only", "both", "coverage", "regenerate"],
        default="coverage",
        help="Operation mode: check-only (validate existing), populate-only (add missing), both (validate + populate), coverage (report only, default), regenerate (delete and regenerate, supports --batch)",
    )

    # Language selection (multiple)
    parser.add_argument(
        "--language",
        "--languages",
        nargs="+",
        dest="languages",
        choices=list(LANGUAGE_FIELDS.keys()),
        help="Specific language(s) to process (lt, zh, ko, fr, es, de, pt, sw, vi). Can specify multiple languages separated by spaces. If not specified, processes all languages.",
    )

    # Additional parameters
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Minimum confidence to flag issues (0.0-1.0, default: 0.7)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use batch mode (supported by --mode regenerate only): queue requests instead of making synchronous API calls",
    )
    parser.add_argument(
        "--batch-submit", action="store_true", help="Submit all pending batch requests to OpenAI"
    )
    parser.add_argument(
        "--batch-status",
        type=str,
        metavar="BATCH_ID",
        help="Check status of a submitted batch (requires only batch ID)",
    )
    parser.add_argument(
        "--batch-retrieve",
        type=str,
        metavar="BATCH_ID",
        help="Retrieve and process results from a completed batch (requires only batch ID)",
    )
    return parser


def main():
    """Main entry point for the voras agent."""
    # Import here to avoid circular imports
    from agents.voras.agent import VorasAgent
    from wordfreq.storage.models.schema import Lemma, LemmaTranslation

    parser = get_argument_parser()
    args = parser.parse_args()

    # Validate cache arguments
    validate_cache_args(args)

    # Create data source configuration (includes backend, cache, and LLM model)
    config = get_data_source_config(args, default_model="gpt-5-mini")

    # Create agent with unified configuration
    agent = VorasAgent(config=config, debug=args.debug)

    # Handle --guid mode (single lemma)
    if args.guid:
        session = agent.get_session()
        try:
            lemma = session.query(Lemma).filter(Lemma.guid == args.guid).first()
            if not lemma:
                print(f"\nError: No lemma found with GUID: {args.guid}")
                sys.exit(1)

            print(f"\nProcessing translations for: {lemma.lemma_text} (GUID: {args.guid})")
            print(f"POS: {lemma.pos_type}")
            print(f"Definition: {lemma.definition_text or 'N/A'}")
            print("\nCurrent translations:")

            # Import here to get language names
            from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS

            # Show all translations
            missing_langs = []
            for lang_code in LANGUAGE_FIELDS.keys():
                translation = agent.get_translation(session, lemma, lang_code)
                lang_name = LANGUAGE_FIELDS[lang_code][1]
                if translation:
                    print(f"  {lang_name} ({lang_code}): {translation}")
                else:
                    print(f"  {lang_name} ({lang_code}): [MISSING]")
                    missing_langs.append(lang_code)

            # If in populate mode or mode is "both", offer to populate missing
            if args.mode in ["populate-only", "both"] and missing_langs:
                print(f"\nMissing translations: {', '.join(missing_langs)}")
                if not args.dry_run:
                    print("Generating missing translations...")

                    # Try cache first if available
                    response = None
                    cache_client = agent.get_cache_client()
                    if cache_client:
                        try:
                            cached_translations = cache_client.get_translations(lemma.guid)
                            if cached_translations:
                                print("  Using cached translations from BARSUKAS server")
                                response = cached_translations
                        except Exception as cache_error:
                            print(f"  Cache lookup failed: {cache_error}")
                            if agent.config.cache_only:
                                raise

                    # If no cache hit, query LLM
                    if not response:
                        if agent.config.cache_only:
                            print("\n✗ Cache-only mode: cannot generate translations (not in cache)")
                        else:
                            client = agent.get_linguistic_client()
                            try:
                                response = client.get_translations(
                                    word=lemma.lemma_text,
                                    definition=lemma.definition_text,
                                    pos_type=lemma.pos_type,
                                )
                            except Exception as e:
                                print(f"\nError generating translations: {e}")
                                session.rollback()
                                response = None

                    if response:
                        print("\nGenerated translations:")
                        for lang_code in missing_langs:
                            field_name = LANGUAGE_FIELDS[lang_code][0]
                            if lang_code in response and response[lang_code]:
                                agent.set_translation(session, lemma, lang_code, response[lang_code])
                                print(f"  {LANGUAGE_FIELDS[lang_code][1]} ({lang_code}): {response[lang_code]}")
                        session.commit()
                        print("\n✓ Translations saved")
                    else:
                        print("\nFailed to generate translations")
                else:
                    print("[DRY RUN] Would generate missing translations")
        finally:
            session.close()
        return

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
    if args.mode == "regenerate":
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
                    print(
                        f"  2. Queue {word_count} batch requests (1 per word) for later submission"
                    )
                    print(f"\nModel: {args.model}")
                    print(f"Words to process: {word_count}")
                    print(
                        f"\nBatch mode: Requests will be queued locally, then submitted with --batch-submit"
                    )
                else:
                    print(
                        f"  2. Regenerate them fresh using {word_count} LLM API calls (1 per word)"
                    )
                    print(f"\nModel: {args.model}")
                    print(f"Words to process: {word_count}")
                    print("\nThis may incur costs and take some time to complete.")
                response = input("Do you want to proceed? [y/N]: ").strip().lower()

                if response not in ["y", "yes"]:
                    print("Aborted.")
                    sys.exit(0)
                print()
            finally:
                session.close()

        # Execute regeneration
        results = agent.regenerate_all_translations(
            limit=args.limit, dry_run=args.dry_run, batch_mode=args.batch
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
            print(f"  1. Submit batch: python -m agents.voras --batch-submit")
            print(f"  2. Check status: python -m agents.voras --batch-status <batch_id>")
            print(f"  3. Retrieve results: python -m agents.voras --batch-retrieve <batch_id>")
        else:
            print("REGENERATION COMPLETE")
            print("=" * 80)
            print(f"Words processed: {results['total_words_processed']}")
            print(f"Total translations added: {results['total_translations_added']}")
            print(f"Total failed: {results['total_failed']}")
            print()
            for lang_code, lang_results in results["by_language"].items():
                print(f"{lang_results['language_name']}:")
                print(f"  Deleted: {lang_results['deleted']}")
                print(f"  Added: {lang_results['added']}")
                print(f"  Failed: {lang_results['failed']}")
        print("=" * 80)
        return

    # Handle different modes
    if args.mode == "coverage":
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
            # args.languages is now a list or None
            languages_to_process = args.languages if args.languages else list(LANGUAGE_FIELDS.keys())

            if args.mode in ["check-only", "both"]:
                # Calculate validation calls
                if args.languages and len(args.languages) == 1:
                    # Single language: still validates all languages per word, just filters which words
                    field_name, language_name, use_translation_table = LANGUAGE_FIELDS[
                        args.languages[0]
                    ]
                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None),
                        getattr(Lemma, field_name).isnot(None),
                        getattr(Lemma, field_name) != "",
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    count = query.count()
                    if args.sample_rate < 1.0:
                        count = int(count * args.sample_rate)
                    estimated_calls += count
                    logger.info(
                        f"{language_name}: {count} words to validate (all translations per word)"
                    )
                elif args.languages and len(args.languages) > 1:
                    # Multiple languages: validate words that have ANY of the specified language translations
                    has_translation_filter = None
                    for lang_code in args.languages:
                        field_name, _, use_translation_table = LANGUAGE_FIELDS[lang_code]
                        field_filter = (getattr(Lemma, field_name).isnot(None)) & (
                            getattr(Lemma, field_name) != ""
                        )
                        if has_translation_filter is None:
                            has_translation_filter = field_filter
                        else:
                            has_translation_filter = has_translation_filter | field_filter

                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None), has_translation_filter
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    count = query.count()
                    if args.sample_rate < 1.0:
                        count = int(count * args.sample_rate)
                    estimated_calls += count
                    lang_names = ", ".join([LANGUAGE_FIELDS[lc][1] for lc in args.languages])
                    logger.info(
                        f"{lang_names}: {count} words to validate (all translations per word)"
                    )
                else:
                    # All languages: one call per word with any translation
                    has_translation_filter = None
                    for lang_code, (field_name, _) in LANGUAGE_FIELDS.items():
                        field_filter = (getattr(Lemma, field_name).isnot(None)) & (
                            getattr(Lemma, field_name) != ""
                        )
                        if has_translation_filter is None:
                            has_translation_filter = field_filter
                        else:
                            has_translation_filter = has_translation_filter | field_filter

                    query = session.query(Lemma).filter(
                        Lemma.guid.isnot(None), has_translation_filter
                    )
                    if args.limit:
                        query = query.limit(args.limit)
                    count = query.count()
                    if args.sample_rate < 1.0:
                        count = int(count * args.sample_rate)
                    estimated_calls += count
                    logger.info(
                        f"All languages: {count} words to validate (all translations per word)"
                    )

            if args.mode in ["populate-only", "both"]:
                # Calculate population calls - one call per word with any missing translation
                # Note: For LemmaTranslation-based languages, we can't easily build a SQL filter
                # So we just query all lemmas and count missing translations in Python
                query = session.query(Lemma).filter(Lemma.guid.isnot(None))
                if args.limit:
                    query = query.limit(args.limit)

                all_lemmas = query.all()

                # Count words that have at least one missing translation
                words_with_missing = []
                for lemma in all_lemmas:
                    has_missing = False
                    for lang_code in languages_to_process:
                        field_name, language_name, use_translation_table = LANGUAGE_FIELDS[
                            lang_code
                        ]

                        if use_translation_table:
                            # Check LemmaTranslation table
                            translation_obj = (
                                session.query(LemmaTranslation)
                                .filter(
                                    LemmaTranslation.lemma_id == lemma.id,
                                    LemmaTranslation.language_code == field_name,
                                )
                                .first()
                            )
                            translation = translation_obj.translation if translation_obj else None
                        else:
                            # Check Lemma table column
                            translation = getattr(lemma, field_name, None)

                        if not translation or not translation.strip():
                            has_missing = True
                            break

                    if has_missing:
                        words_with_missing.append(lemma)

                count = len(words_with_missing)
                estimated_calls += count

                # Count missing per language for reporting
                for lang_code in languages_to_process:
                    field_name, language_name, use_translation_table = LANGUAGE_FIELDS[lang_code]

                    missing_count = 0
                    for lemma in words_with_missing:
                        if use_translation_table:
                            translation_obj = (
                                session.query(LemmaTranslation)
                                .filter(
                                    LemmaTranslation.lemma_id == lemma.id,
                                    LemmaTranslation.language_code == field_name,
                                )
                                .first()
                            )
                            translation = translation_obj.translation if translation_obj else None
                        else:
                            translation = getattr(lemma, field_name, None)

                        if not translation or not translation.strip():
                            missing_count += 1

                    logger.info(
                        f"{language_name}: {missing_count} missing translations to populate"
                    )

                if args.cache_only:
                    logger.info(
                        f"Total: {count} words to populate (using cached translations only)"
                    )
                else:
                    logger.info(
                        f"Total: {count} words to populate (1 LLM call per word for all missing translations)"
                    )

        finally:
            session.close()

        if args.cache_only:
            print(f"\nCache-only mode: Will use cached translations from {args.barsukas_url}")
            print("No LLM API calls will be made.")
        else:
            print(
                f"\nThis will make approximately {estimated_calls} LLM API calls using model '{args.model}'."
            )
            print("This may incur costs and take some time to complete.")
        response = input("Do you want to proceed? [y/N]: ").strip().lower()

        if response not in ["y", "yes"]:
            print("Aborted.")
            sys.exit(0)

        print()  # Extra newline for readability

    # Execute the requested mode
    results = {}

    if args.mode == "check-only":
        # Validate existing translations
        if args.languages and len(args.languages) == 1:
            # Single language validation
            results = agent.validate_translations(
                args.languages[0],
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )
            print(f"\n{results['language_name']} validation results:")
            print(f"  Issues found: {results['issues_found']} out of {results['total_checked']}")
            print(f"  Issue rate: {results['issue_rate']:.1f}%")
        else:
            # All languages or multiple languages - use validate_all (which checks all translations per word)
            results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )
            if args.languages and len(args.languages) > 1:
                lang_names = ", ".join([LANGUAGE_FIELDS[lc][1] for lc in args.languages])
                print(f"\nValidation results for {lang_names}:")
                print(
                    f"  Total translation issues (all languages): {results['total_issues_all_languages']}"
                )
            else:
                print(
                    f"\nTotal translation issues (all languages): {results['total_issues_all_languages']}"
                )

    elif args.mode == "populate-only":
        # Generate missing translations only
        results = agent.fix_missing_translations(
            language_code=args.languages, limit=args.limit, dry_run=args.dry_run
        )
        print("\n" + "=" * 80)
        print("TRANSLATION POPULATION SUMMARY")
        print("=" * 80)
        for lang_code, lang_results in results["by_language"].items():
            print(f"\n{lang_results['language_name']}:")
            print(f"  Total missing: {lang_results['total_missing']}")
            print(f"  Populated: {lang_results['fixed']}")
            print(f"  Failed: {lang_results['failed']}")
        print(f"\nTotal populated: {results['total_fixed']}")
        print(f"Total failed: {results['total_failed']}")
        print("=" * 80)

    elif args.mode == "both":
        # First validate existing translations
        print("\n=== STEP 1: Validating Existing Translations ===\n")
        if args.languages and len(args.languages) == 1:
            # Single language validation
            validation_results = agent.validate_translations(
                args.languages[0],
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )
        else:
            # All languages or multiple languages
            validation_results = agent.validate_all_translations(
                limit=args.limit,
                sample_rate=args.sample_rate,
                confidence_threshold=args.confidence_threshold,
            )

        # Then populate missing translations
        print("\n=== STEP 2: Populating Missing Translations ===\n")
        population_results = agent.fix_missing_translations(
            language_code=args.languages, limit=args.limit, dry_run=args.dry_run
        )

        # Combined summary
        print("\n" + "=" * 80)
        print("COMBINED VALIDATION + POPULATION SUMMARY")
        print("=" * 80)

        if args.languages and len(args.languages) == 1:
            # Single language validation results
            print(f"\nValidation ({validation_results['language_name']}):")
            print(
                f"  Issues found: {validation_results['issues_found']} out of {validation_results['total_checked']}"
            )
            print(f"  Issue rate: {validation_results['issue_rate']:.1f}%")
        else:
            # All languages or multiple languages validation results
            if args.languages and len(args.languages) > 1:
                lang_names = ", ".join([LANGUAGE_FIELDS[lc][1] for lc in args.languages])
                print(f"\nValidation ({lang_names}):")
            else:
                print(f"\nValidation (all languages):")
            print(f"  Total issues: {validation_results['total_issues_all_languages']}")

        print(f"\nPopulation:")
        for lang_code, lang_results in population_results["by_language"].items():
            print(
                f"  {lang_results['language_name']}: {lang_results['fixed']} populated, {lang_results['failed']} failed"
            )
        print("=" * 80)


if __name__ == "__main__":
    main()
