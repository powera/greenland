"""
Voras Agent - Display and Output Formatting

This module handles all console output and display formatting.
"""

import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS, get_language_name


def print_regeneration_summary(results, batch_mode=False):
    """Print summary of regeneration results."""
    print("\n" + "=" * 80)
    if batch_mode:
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
        for lang_code, lang_results in results['by_language'].items():
            print(f"{lang_results['language_name']}:")
            print(f"  Deleted: {lang_results['deleted']}")
            print(f"  Added: {lang_results['added']}")
            print(f"  Failed: {lang_results['failed']}")
    print("=" * 80)


def print_validation_summary(results, language_code=None):
    """Print validation results summary."""
    if language_code:
        print(f"\n{results['language_name']} validation results:")
        print(f"  Issues found: {results['issues_found']} out of {results['total_checked']}")
        print(f"  Issue rate: {results['issue_rate']:.1f}%")
    else:
        print(f"\nTotal translation issues (all languages): {results['total_issues_all_languages']}")


def print_population_summary(results):
    """Print population/fixing results summary."""
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


def print_combined_summary(validation_results, population_results, language_code=None):
    """Print combined validation and population summary."""
    print("\n" + "=" * 80)
    print("COMBINED VALIDATION + POPULATION SUMMARY")
    print("=" * 80)

    if language_code:
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
