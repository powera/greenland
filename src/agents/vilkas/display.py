"""
Vilkas Agent - Display and Output Formatting

This module handles all console output and display formatting.
"""


def print_fix_confirmation(lang_name, form_type, needs_fix, args):
    """
    Print confirmation prompt for fix operations.

    Returns:
        bool: True if user confirmed, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Ready to generate missing {lang_name} {form_type}")
    print(f"Total needing fix: {needs_fix}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print(f"Model: {args.model}")
    if args.language == "lt":
        print(f"Source: {args.source}")
    print(f"Throttle: {args.throttle}s between calls")
    print(f"{'='*60}")
    response = input("\nContinue? [y/N]: ")
    return response.lower() in ["y", "yes"]


def print_fix_results(results, dry_run=False):
    """Print results of fix operation."""
    if "error" in results:
        print(f"\nError: {results['error']}")
        if "supported_languages" in results:
            print(f"Supported languages: {', '.join(results['supported_languages'])}")
        if "supported_pos_types" in results:
            print(f"Supported POS types: {', '.join(results['supported_pos_types'])}")
    else:
        if dry_run:
            print(
                f"\nDRY RUN: Would process {results['would_process']} items out of {results['total_needing_fix']} total"
            )
        else:
            print(f"\nFix complete:")
            print(f"  Total needing fix: {results['total_needing_fix']}")
            print(f"  Processed: {results['processed']}")
            print(f"  Successful: {results['successful']}")
            print(f"  Failed: {results['failed']}")


def print_base_forms_check(results):
    """Print base forms check results."""
    print(
        f"\nMissing base forms: {results['missing_count']} out of {results['total_with_translation']}"
    )
    print(f"Coverage: {results['coverage_percentage']:.1f}%")


def print_noun_declensions_check(results):
    """Print noun declensions check results."""
    print(
        f"\nNouns needing declensions: {results['needs_declensions']} out of {results['total_nouns']}"
    )
    print(f"Coverage: {results['declension_coverage_percentage']:.1f}%")


def print_verb_conjugations_check(results, language_code):
    """Print verb conjugations check results."""
    lang_name = results.get("language_name", language_code.upper())
    print(
        f"\n{lang_name} Verbs needing conjugations: {results['needs_conjugations']} out of {results['total_verbs']}"
    )
    print(f"Coverage: {results['conjugation_coverage_percentage']:.1f}%")
