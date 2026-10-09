"""Display utilities specific to the VORAS agent CLI.

This module contains display functions for VORAS-specific output formats,
keeping the main CLI clean and focused on logic.
"""

from typing import Any, Dict, List, Optional

from storage.translation_helpers import LANGUAGE_FIELDS


def display_lemma_translations(lemma: Any, translations: Dict[str, Optional[str]]) -> None:
    """Display a lemma's current translations, marking the missing ones.

    Args:
        lemma: Lemma object to display
        translations: Language code -> translation (or None), as returned by
            ``TranslationWorkflow.collect_translations``
    """
    print(f"\nProcessing translations for: {lemma.lemma_text} (GUID: {lemma.guid})")
    print(f"POS: {lemma.pos_type}")
    print(f"Definition: {lemma.definition_text or 'N/A'}")
    print("\nCurrent translations:")

    for lang_code in LANGUAGE_FIELDS.keys():
        translation = translations.get(lang_code)
        lang_name = LANGUAGE_FIELDS[lang_code][1]
        if translation:
            print(f"  {lang_name} ({lang_code}): {translation}")
        else:
            print(f"  {lang_name} ({lang_code}): [MISSING]")


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
        if lang_results.get("uncertain"):
            print(f"  Below confidence: {lang_results['uncertain']}")
    print(f"\nTotal populated: {results['total_fixed']}")
    print(f"Total failed: {results['total_failed']}")
    if results.get("total_uncertain"):
        print(f"Below confidence (recorded as uncertain): {results['total_uncertain']}")
    if results.get("total_uncertain_skipped"):
        print(
            f"Skipped as uncertain: {results['total_uncertain_skipped']} "
            "(--retry-uncertain to ask again)"
        )
    print("=" * 80)
