"""Subject-pronoun data for it."""

from __future__ import annotations


_SUBJECT_PRONOUNS_BY_PERSON: dict[str, list[str]] = {
    "1s": ["io"],
    "2s": ["tu"],
    "3s": ["lui", "lei"],
    "1p": ["noi"],
    "2p": ["voi"],
    "3p": ["loro"],
}


def get_subject_pronouns_by_person() -> dict[str, list[str]]:
    """Return subject pronouns grouped by grammatical person slot."""
    return _SUBJECT_PRONOUNS_BY_PERSON
