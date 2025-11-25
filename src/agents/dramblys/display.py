"""
Dramblys Agent - Display and Output Formatting

This module handles all console output and display formatting.
"""


def print_pending_imports_list(results):
    """Print list of pending imports."""
    if "error" in results:
        print(f"\nError: {results['error']}")
        return

    print(f"\n{'='*80}")
    print(f"PENDING IMPORTS: {results['count']} entries")
    print(f"{'='*80}\n")

    for i, pending in enumerate(results["pending_imports"], 1):
        print(f"{i}. ID {pending['id']}: '{pending['english_word']}'")
        print(f"   Definition: {pending['definition'][:80]}...")
        print(f"   Translation ({pending['language']}): {pending['translation']}")
        if pending["pos_type"]:
            print(f"   POS: {pending['pos_type']}/{pending['pos_subtype']}")
        if pending["frequency_rank"]:
            print(f"   Frequency rank: {pending['frequency_rank']}")
        print(f"   Source: {pending['source']}")
        print()


def print_approval_result(results):
    """Print approval/rejection result."""
    if results["success"]:
        print(f"\nSuccess: {results['message']}")
        if results.get("added_to_exclusions"):
            print(f"  Added '{results['word']}' to exclusions")
    else:
        print(f"\nError: {results.get('error', 'Unknown error')}")


def print_staging_summary(results, dry_run=False):
    """Print staging operation summary."""
    if "error" in results:
        print(f"\nError: {results['error']}")
        return

    if dry_run:
        print(f"\nDRY RUN: Would stage {results['would_stage']} words out of {results['total_missing']} total")
    else:
        print(f"\nStaging complete:")
        print(f"  Total missing: {results['total_missing']}")
        print(f"  Processed: {results['processed']}")
        print(f"  Staged: {results['staged']}")
        print(f"  Skipped (already pending): {results['skipped_already_pending']}")
        print(f"  Failed: {results['failed']}")
        print(f"\nUse --list-pending to review staged words")


def print_subtype_find_results(results, pos_type, pos_subtype):
    """Print results of finding words for a subtype."""
    if "error" in results:
        print(f"\nError: {results['error']}")
        return

    print(f"\n{'='*80}")
    print(f"FOUND {results['matches_found']} {pos_type.upper()} WORDS FOR SUBTYPE: {pos_subtype}")
    print(f"Reviewed top {results['total_words_reviewed']} frequency words")
    print(f"{'='*80}\n")

    for i, match in enumerate(results["matches"], 1):
        print(f"{i}. '{match['word']}' - {match['definition']}")
        print(f"   Confidence: {match.get('confidence', 'N/A')}\n")


def print_subtype_add_results(results, dry_run=False, stage_only=False):
    """Print results of adding words for a subtype."""
    if "error" in results:
        print(f"\nError: {results['error']}")
        return

    if dry_run:
        action = "stage" if stage_only else "add"
        print(f"\nDRY RUN: Would {action} {results['would_add']} words")
    else:
        print(f"\nComplete:")
        print(f"  Matches found: {results['matches_found']}")
        if stage_only:
            print(f"  Staged: {results['staged']}")
            print(f"\nUse --list-pending to review staged words")
        else:
            print(f"  Successfully added: {results['successful']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Skipped (already exist): {results['skipped']}")


def print_fix_missing_summary(results, dry_run=False):
    """Print summary of fix missing words operation."""
    if "error" in results:
        print(f"\nError: {results['error']}")
        return

    if dry_run:
        print(f"\nDRY RUN: Would process {results['would_process']} words out of {results['total_missing']} total")
    else:
        print(f"\nFix complete:")
        print(f"  Total missing: {results['total_missing']}")
        print(f"  Processed: {results['processed']}")
        print(f"  Successful: {results['successful']}")
        print(f"  Failed: {results['failed']}")


def print_check_summary(check_type, results):
    """Print summary of check operations."""
    if check_type == "orphaned":
        print(f"\nOrphaned derivative forms: {results['orphaned_count']} out of {results['total_forms_checked']}")
    elif check_type == "subtypes":
        print(f"\nUnder-covered subtypes: {results['under_covered_count']} out of {results['total_subtypes']}")
    elif check_type == "levels":
        print(f"\nEmpty difficulty levels: {len(results['gaps'])}")
        print(f"Imbalanced levels: {len(results['imbalanced'])}")


def print_confirmation_prompt(prompt_type, **kwargs):
    """Print confirmation prompts for various operations.

    Returns:
        bool: True if user confirmed, False otherwise
    """
    if prompt_type == "stage":
        print(f"\n{'='*60}")
        print(f"Ready to stage high-frequency missing words")
        print(f"Total missing words found: {kwargs.get('total_missing', 0)}")
        if kwargs.get("limit"):
            print(f"Limit: {kwargs['limit']} words")
        print(f"Model: {kwargs.get('model', 'N/A')}")
        print(f"Target language: {kwargs.get('target_language', 'N/A')}")
        print(f"Throttle: {kwargs.get('throttle', 1.0)}s between calls")
        print(f"\nWords will be added to pending_imports for review")
        print(f"{'='*60}")

    elif prompt_type == "add_subtype":
        print(f"\n{'='*60}")
        print(f"Found {kwargs.get('matches_found', 0)} {kwargs.get('pos_type')} words for subtype '{kwargs.get('pos_subtype')}'")
        print(f"Model: {kwargs.get('model', 'N/A')}")
        print(f"Throttle: {kwargs.get('throttle', 1.0)}s between calls")
        print(f"\nSample words:")
        for match in kwargs.get("sample_matches", [])[:5]:
            print(f"  - '{match['word']}': {match['definition'][:60]}...")
        print(f"{'='*60}")

    elif prompt_type == "fix":
        print(f"\n{'='*60}")
        print(f"Ready to process high-frequency missing words using LLM")
        print(f"Total missing words found: {kwargs.get('total_missing', 0)}")
        if kwargs.get("limit"):
            print(f"Limit: {kwargs['limit']} words")
        print(f"Model: {kwargs.get('model', 'N/A')}")
        print(f"Throttle: {kwargs.get('throttle', 1.0)}s between calls")
        print(f"\nThis will:")
        print(f"  - Query LLM for definitions, lemmas, and POS info")
        print(f"  - Handle plurals, polysemous words, and grammatical words")
        print(f"  - Create multiple lemmas for words with multiple meanings")
        print(f"  - Correctly identify base forms vs. inflected forms")
        print(f"{'='*60}")

    response = input("\nContinue? [y/N]: ")
    return response.lower() in ["y", "yes"]
