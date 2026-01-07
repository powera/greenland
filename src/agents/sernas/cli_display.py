"""Display utilities specific to the SERNAS agent CLI.

This module contains display functions for SERNAS-specific output formats,
keeping the main CLI clean and focused on logic.
"""

from typing import Dict, Any


def display_synonym_results(result: Dict[str, Any], dry_run: bool = False) -> None:
    """Display results from synonym/alternative form generation.

    Args:
        result: Dictionary with generation results containing:
                - synonyms: List of synonyms
                - abbreviations: List of abbreviations
                - expanded_forms: List of expanded forms
                - alternate_spellings: List of alternate spellings
        dry_run: If True, show as dry run output

    Example:
        result = {
            "synonyms": ["road", "avenue"],
            "abbreviations": ["St"],
            "expanded_forms": ["Street"],
            "alternate_spellings": []
        }
        display_synonym_results(result, dry_run=True)
    """
    prefix = "\n[DRY RUN] Would generate:" if dry_run else "\n✓ Generated and saved:"
    print(prefix)

    if result.get("synonyms"):
        print(f"  Synonyms: {', '.join(result['synonyms'])}")
    if result.get("abbreviations"):
        print(f"  Abbreviations: {', '.join(result['abbreviations'])}")
    if result.get("expanded_forms"):
        print(f"  Expanded forms: {', '.join(result['expanded_forms'])}")
    if result.get("alternate_spellings"):
        print(f"  Alternate spellings: {', '.join(result['alternate_spellings'])}")


def display_batch_results(
    results: Dict[str, Any], language_code: str, dry_run: bool = False
) -> None:
    """Display results from batch processing operations.

    Args:
        results: Dictionary with batch results containing:
                 - total_needing_fix: Total items that needed processing
                 - processed: Number of items processed
                 - successful: Number of successful operations
                 - failed: Number of failed operations
                 - would_process: (dry run only) Number that would be processed
        language_code: Language code being processed
        dry_run: If True, show as dry run output

    Example:
        results = {"total_needing_fix": 100, "processed": 50, "successful": 48, "failed": 2}
        display_batch_results(results, "en", dry_run=False)
    """
    print(f"\n{'='*60}")
    if dry_run:
        print(f"DRY RUN COMPLETE - {language_code.upper()}")
        print(f"Would process: {results.get('would_process', 0)} lemmas")
    else:
        print(f"FIX COMPLETE - {language_code.upper()}")
        print(f"Total needing fix: {results.get('total_needing_fix', 0)}")
        print(f"Processed: {results.get('processed', 0)}")
        print(f"Successful: {results.get('successful', 0)}")
        print(f"Failed: {results.get('failed', 0)}")
    print(f"{'='*60}")
