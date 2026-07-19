#!/usr/bin/python3

"""Shared in-process runner for BEBRAS integrity checks.

Used by the Quality Hub and the Data Quality (bebras) pages so both can run
individual integrity checks directly against the app database without
launching an agent subprocess.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from flask import current_app

from agents.bebras.integrity import IntegrityChecker
from storage.backend.config import BackendType

# (check_id, display name, description) for every check runnable in-process.
INTEGRITY_CHECKS: List[Tuple[str, str, str]] = [
    (
        "orphaned",
        "Orphaned Records",
        "Derivative forms or word frequencies pointing to deleted lemmas/tokens",
    ),
    (
        "missing-fields",
        "Missing Fields",
        "Lemmas missing a definition, part of speech, or difficulty level",
    ),
    (
        "no-derivatives",
        "No Derivatives",
        "Lemmas that have no inflected forms (e.g. no plural, no conjugations)",
    ),
    ("duplicates", "Duplicate GUIDs", "Two or more lemmas sharing the same GUID identifier"),
    (
        "duplicate-words",
        "Duplicate Words",
        "Lemmas with the same text and part of speech that may need merging",
    ),
    (
        "invalid-levels",
        "Invalid Levels",
        "Difficulty levels outside the valid 1–20 range",
    ),
    (
        "missing-punctuation",
        "Missing Punctuation",
        "Sentence translations not ending with a period, question mark, or exclamation mark",
    ),
    (
        "sentence-levels",
        "Sentence Levels",
        "Sentences whose minimum_level doesn't match their linked word difficulties",
    ),
    (
        "audio-mismatches",
        "Audio Mismatches",
        "Audio files whose expected text no longer matches the current translation",
    ),
    (
        "pronunciation-fields",
        "Pronunciation Fields",
        "IPA fields that look like leaked prompts/instructions instead of pronunciations",
    ),
]

# Checks that support --fix / fix=True
FIXABLE_CHECKS = {
    "missing-punctuation",
    "sentence-levels",
    "audio-mismatches",
    "pronunciation-fields",
}


def checker_db_path() -> Optional[str]:
    """Get the integrity checker db path from the app backend configuration."""
    backend_config = current_app.backend_config  # type: ignore[attr-defined]
    if backend_config.backend_type == BackendType.SQLITE:
        return cast(Optional[str], backend_config.sqlite_path)
    return None


def run_integrity_check(check_type: str, fix: bool = False) -> Optional[Dict[str, Any]]:
    """Run a single named integrity check in-process.

    Returns the check's result dict, or None if check_type is unknown.
    """
    checker = IntegrityChecker(db_path=checker_db_path())

    check_map: Dict[str, Callable[[], Dict[str, Any]]] = {
        "orphaned": lambda: {
            "derivative_forms": checker.check_orphaned_derivative_forms(),
            "derivative_form_word_tokens": checker.check_derivative_form_word_tokens(),
        },
        "missing-fields": checker.check_missing_required_fields,
        "no-derivatives": checker.check_lemmas_without_derivatives,
        "duplicates": checker.check_duplicate_guids,
        "duplicate-words": checker.check_duplicate_words,
        "invalid-levels": checker.check_invalid_difficulty_levels,
        "missing-punctuation": lambda: checker.check_sentences_missing_punctuation(fix=fix),
        "sentence-levels": lambda: checker.check_sentence_levels(fix=fix),
        "audio-mismatches": lambda: checker.check_audio_translation_mismatches(fix=fix),
        "pronunciation-fields": lambda: checker.check_pronunciation_fields(fix=fix),
    }

    runner = check_map.get(check_type)
    if runner is None:
        return None
    return runner()
