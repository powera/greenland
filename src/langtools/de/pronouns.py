"""Subject-pronoun data for de."""

from __future__ import annotations


_SUBJECT_PRONOUNS_BY_PERSON: dict[str, list[str]] = {
    "1s": ["ich"],
    "2s": ["du"],
    "3s": ["er", "sie", "es"],
    "1p": ["wir"],
    "2p": ["ihr"],
    "3p": ["sie", "Sie"],
}


def get_subject_pronouns_by_person() -> dict[str, list[str]]:
    """Return subject pronouns grouped by grammatical person slot."""
    return _SUBJECT_PRONOUNS_BY_PERSON
