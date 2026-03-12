"""Subject-pronoun data for en."""

from __future__ import annotations


_SUBJECT_PRONOUNS_BY_PERSON: dict[str, list[str]] = {
    "1s": ["I"],
    "2s": ["you"],
    "3s": ["he", "she", "it"],
    "1p": ["we"],
    "2p": ["you"],
    "3p": ["they"],
}


def get_subject_pronouns_by_person() -> dict[str, list[str]]:
    """Return subject pronouns grouped by grammatical person slot."""
    return _SUBJECT_PRONOUNS_BY_PERSON
