"""Display utilities specific to the VORAS agent CLI.

This module contains display functions for VORAS-specific output formats,
keeping the main CLI clean and focused on logic.
"""

from typing import Any, Dict, List

from wordfreq.storage.translation_helpers import LANGUAGE_FIELDS


def display_lemma_translations(lemma: Any, agent: Any, session: Any) -> List[str]:
    """Display current translations for a lemma and return list of missing languages.

    Args:
        lemma: Lemma object to display
        agent: VorasAgent instance
        session: Database session

    Returns:
        List of language codes for missing translations
    """
    print(f"\nProcessing translations for: {lemma.lemma_text} (GUID: {lemma.guid})")
    print(f"POS: {lemma.pos_type}")
    print(f"Definition: {lemma.definition_text or 'N/A'}")
    print("\nCurrent translations:")

    missing_langs = []
    for lang_code in LANGUAGE_FIELDS.keys():
        translation = agent.get_translation(session, lemma, lang_code)
        lang_name = LANGUAGE_FIELDS[lang_code][1]
        if translation:
            print(f"  {lang_name} ({lang_code}): {translation}")
        else:
            print(f"  {lang_name} ({lang_code}): [MISSING]")
            missing_langs.append(lang_code)

    return missing_langs


def display_generated_translations(response: Dict[str, str], missing_langs: List[str]) -> None:
    """Display newly generated translations.

    Args:
        response: Dictionary mapping language codes to translations
        missing_langs: List of language codes that were missing
    """
    print("\nGenerated translations:")
    for lang_code in missing_langs:
        field_name = LANGUAGE_FIELDS[lang_code][0]
        if lang_code in response and response[lang_code]:
            print(f"  {LANGUAGE_FIELDS[lang_code][1]} ({lang_code}): {response[lang_code]}")


def display_batch_summary(results: Dict[str, Any], batch_mode: bool = False) -> None:
    """Display summary of batch translation operations.

    Args:
        results: Dictionary with batch results
        batch_mode: If True, display batch-specific information
    """
    print("\n" + "=" * 80)
    if batch_mode:
        print("BATCH QUEUE COMPLETE")
        print("=" * 80)
        print(f"Words processed: {results['total_words_processed']}")
        print(f"Batch requests queued: {results.get('batch_requests_queued', 0)}")
        print()
        print("Next steps:")
        print("  1. Submit batch: python -m agents.voras --batch-submit")
        print("  2. Check status: python -m agents.common.batch status --batch-id <batch_id>")
        print("  3. Complete batch: python -m agents.common.batch complete --batch-id <batch_id>")
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


def display_population_summary(results: Dict[str, Any]) -> None:
    """Display summary of translation population operations.

    Args:
        results: Dictionary with population results by language
    """
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


def display_validation_summary(results: Dict[str, Any], languages: List[str]) -> None:
    """Display summary of validation operations.

    Args:
        results: Dictionary with validation results
        languages: List of language codes validated
    """
    if len(languages) == 1:
        # Single language validation
        print(f"\n{results['language_name']} validation results:")
        print(f"  Issues found: {results['issues_found']} out of {results['total_checked']}")
        print(f"  Issue rate: {results['issue_rate']:.1f}%")
    else:
        # Multiple languages validation
        if len(languages) > 1:
            lang_names = ", ".join([LANGUAGE_FIELDS[lc][1] for lc in languages])
            print(f"\nValidation results for {lang_names}:")
        else:
            print(f"\nValidation results (all languages):")
        print(f"  Total translation issues: {results['total_issues_all_languages']}")


def display_combined_summary(
    validation_results: Dict[str, Any], population_results: Dict[str, Any], languages: List[str]
) -> None:
    """Display combined summary for both validation and population.

    Args:
        validation_results: Dictionary with validation results
        population_results: Dictionary with population results
        languages: List of language codes processed
    """
    print("\n" + "=" * 80)
    print("COMBINED VALIDATION + POPULATION SUMMARY")
    print("=" * 80)

    # Validation results
    if len(languages) == 1:
        print(f"\nValidation ({validation_results['language_name']}):")
        print(
            f"  Issues found: {validation_results['issues_found']} out of {validation_results['total_checked']}"
        )
        print(f"  Issue rate: {validation_results['issue_rate']:.1f}%")
    else:
        if len(languages) > 1:
            lang_names = ", ".join([LANGUAGE_FIELDS[lc][1] for lc in languages])
            print(f"\nValidation ({lang_names}):")
        else:
            print(f"\nValidation (all languages):")
        print(f"  Total issues: {validation_results['total_issues_all_languages']}")

    # Population results
    print(f"\nPopulation:")
    for lang_code, lang_results in population_results["by_language"].items():
        print(
            f"  {lang_results['language_name']}: {lang_results['fixed']} populated, {lang_results['failed']} failed"
        )
    print("=" * 80)
