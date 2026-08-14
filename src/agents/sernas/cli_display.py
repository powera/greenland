"""Display utilities specific to the SERNAS agent CLI.

This module contains display functions for SERNAS-specific output formats,
keeping the main CLI clean and focused on logic.
"""

from typing import Any, Dict, List

from words.synonym_coverage import MissingSynonymLemma, MissingSynonymReport
from words.synonym_workflow import SynonymFixResults
from workqueue.task_queue import EnqueueSummary

# Lemmas listed individually in a coverage report before it is truncated.
SAMPLE_LIMIT: int = 10


def display_synonym_results(result: Dict[str, Any], dry_run: bool = False) -> None:
    """Display results from synonym/alternative form generation.

    Args:
        result: Dictionary with generation results containing:
                - synonyms: List of synonyms
                - abbreviations: List of abbreviations
                - expanded_forms: List of expanded forms
        dry_run: If True, show as dry run output

    Example:
        result = {
            "synonyms": ["road", "avenue"],
            "abbreviations": ["St"],
            "expanded_forms": ["Street"],
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


def display_batch_results(
    results: SynonymFixResults, language_code: str, dry_run: bool = False
) -> None:
    """Display results from batch processing operations.

    Args:
        results: Totals from a fix run.
        language_code: Language code being processed
        dry_run: If True, show as dry run output
    """
    print(f"\n{'='*60}")
    if dry_run:
        print(f"DRY RUN COMPLETE - {language_code.upper()}")
        print(f"Would process: {results.processed} lemmas")
    else:
        print(f"FIX COMPLETE - {language_code.upper()}")
        print(f"Total needing fix: {results.total_needing_fix}")
        print(f"Processed: {results.processed}")
        print(f"Successful: {results.successful}")
        print(f"Failed: {results.failed}")
    print(f"{'='*60}")


def _display_missing_sample(missing: List[MissingSynonymLemma]) -> None:
    """Print the first few lemmas needing forms, noting how many were elided."""
    if not missing:
        return
    print("Sample lemmas needing forms:")
    for index, lemma in enumerate(missing[:SAMPLE_LIMIT], 1):
        print(f"  {index}. {lemma.english} -> {lemma.translation} ({lemma.pos_type})")
    if len(missing) > SAMPLE_LIMIT:
        print(f"  ... and {len(missing) - SAMPLE_LIMIT} more")


def display_language_coverage(report: MissingSynonymReport, language_code: str) -> None:
    """Print the detailed coverage report for a single language."""
    missing = report.for_language(language_code)

    print(f"\n{'='*60}")
    print(f"ŠERNAS AGENT REPORT - {language_code.upper()}")
    print(f"{'='*60}")
    print(f"Lemmas missing forms: {len(missing)}")
    print(f"Checked form types: {', '.join(report.checked_form_types)}")
    print("")

    _display_missing_sample(missing)
    print(f"{'='*60}")


def display_all_language_coverage(report: MissingSynonymReport) -> None:
    """Print the per-language coverage summary across every checked language."""
    print(f"\n{'='*60}")
    print("ŠERNAS AGENT REPORT - Synonyms and Alternative Forms Check")
    print(f"{'='*60}")
    print(f"Total lemmas missing forms: {report.total_missing}")
    print(f"Checked form types: {', '.join(report.checked_form_types)}")
    print("")

    for lang_code in report.checked_languages:
        missing = report.for_language(lang_code)
        print(f"{lang_code.upper()}: {len(missing)} lemmas missing forms")

    print(f"{'='*60}")


def display_enqueue_summary(results: EnqueueSummary) -> None:
    """Print how much work was queued for the barsukas worker."""
    print(f"\nEnqueued: {results['enqueued']}")
    print(f"Skipped: {results['skipped']}")
    if results["dry_run"]:
        print("\n⚠️  DRY RUN - No work items were actually enqueued")
    print("=" * 80)
