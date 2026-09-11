"""Report database integrity problems.

Runs the structural checks in :mod:`storage.integrity` -- orphaned rows, missing
required fields, duplicate GUIDs and words, out-of-range difficulty levels,
sentence-level mismatches, stale audio -- and prints what is wrong.

This report is strictly read-only.  Several of the underlying checks accept a
``fix=True`` that mutates rows, and that is deliberately not exposed here: a
report should be safe to run against any database at any time.  The two
repair paths that are still worth having are reached from the UI instead, where
the surrounding workflow makes the write meaningful -- stale audio is flagged
for regeneration from the Audio Hub, which owns the audio queue.

Usage::

    PYTHONPATH=src python src/reports/integrity.py
    PYTHONPATH=src python src/reports/integrity.py --check duplicates
    PYTHONPATH=src python src/reports/integrity.py --output integrity.json
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.integrity.checker import IntegrityChecker

# (flag value, heading, what a hit means).  Mirrors the list the Barsukas
# integrity runner offers, so the CLI and the UI name the same checks.
CHECKS: List[Tuple[str, str, str]] = [
    ("orphaned", "Orphaned Derivative Forms", "Inflected forms whose lemma no longer exists"),
    ("orphaned-tokens", "Orphaned Form Tokens", "Form-to-token links pointing at a missing form"),
    (
        "missing-fields",
        "Missing Fields",
        "Lemmas missing a definition, part of speech, or difficulty level",
    ),
    ("no-derivatives", "No Derivatives", "Lemmas with no inflected forms"),
    ("duplicates", "Duplicate GUIDs", "Two or more lemmas sharing one GUID"),
    ("duplicate-words", "Duplicate Words", "Same text and part of speech; may need merging"),
    ("invalid-levels", "Invalid Levels", "Difficulty levels outside the valid range"),
    (
        "missing-punctuation",
        "Missing Punctuation",
        "Sentence translations not ending in . ? or !",
    ),
    (
        "sentence-levels",
        "Sentence Levels",
        "Sentences whose minimum_level disagrees with their linked words",
    ),
]

# Each check's method on the storage IntegrityChecker, and the result key holding
# its problem count.  The checks do not share one key, and several also return a
# ``total_checked``-style field that is emphatically *not* a problem count, so
# the right key is named per check rather than guessed from the result.
CHECK_METHODS: Dict[str, Tuple[str, str]] = {
    "orphaned": ("check_orphaned_derivative_forms", "orphaned_count"),
    "orphaned-tokens": ("check_derivative_form_word_tokens", "issue_count"),
    "missing-fields": ("check_missing_required_fields", "total_issues"),
    "no-derivatives": ("check_lemmas_without_derivatives", "without_forms_count"),
    "duplicates": ("check_duplicate_guids", "duplicate_count"),
    "duplicate-words": ("check_duplicate_words", "duplicate_group_count"),
    "invalid-levels": ("check_invalid_difficulty_levels", "invalid_count"),
    "missing-punctuation": ("check_sentences_missing_punctuation", "missing_count"),
    "sentence-levels": ("check_sentence_levels", "issue_count"),
}


def run_checks(checker: IntegrityChecker, check_names: List[str]) -> Dict[str, Any]:
    """Run the named checks and collect their results."""
    results: Dict[str, Any] = {}
    for name in check_names:
        method_name, _ = CHECK_METHODS[name]
        results[name] = getattr(checker, method_name)()
    return results


def _issue_count(check_name: str, result: Any) -> int:
    """Return how many problems a check reported.

    Reads the count key registered for the check.  Falls back to the length of
    the result's single list of offending rows if that key is missing, so a
    check that renames its field reports a wrong-looking number rather than
    silently claiming zero problems.
    """
    if not isinstance(result, dict):
        return 0

    count_key = CHECK_METHODS[check_name][1]
    value = result.get(count_key)
    if isinstance(value, int):
        return value

    lists = [item for item in result.values() if isinstance(item, list)]
    return len(lists[0]) if len(lists) == 1 else 0


def print_report(results: Dict[str, Any], verbose: bool) -> int:
    """Print each check's result. Returns the total number of problems found."""
    headings = {name: heading for name, heading, _ in CHECKS}
    descriptions = {name: description for name, _, description in CHECKS}

    total = 0
    print()
    for name, result in results.items():
        count = _issue_count(name, result)
        total += count
        marker = "OK  " if count == 0 else "FAIL"
        print(f"[{marker}] {headings.get(name, name)}: {count}")
        if count:
            print(f"         {descriptions.get(name, '')}")
        if count and verbose:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    print("\n" + "-" * 60)
    print("No integrity problems found." if total == 0 else f"{total} problem(s) found.")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument(
        "--check",
        action="append",
        choices=[name for name, _, _ in CHECKS],
        help="Run only this check (repeatable). Default: all of them",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print the offending rows, not just counts"
    )
    parser.add_argument("--output", type=Path, help="Also write the results as JSON here")
    args = parser.parse_args()

    config = get_data_source_config(args)
    checker = IntegrityChecker(config)
    check_names = args.check or [name for name, _, _ in CHECKS]
    results = run_checks(checker, check_names)

    print_report(results, args.verbose)
    if args.output is not None:
        args.output.write_text(
            json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
