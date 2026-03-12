"""Subject-pronoun data for fr."""

from __future__ import annotations


_SUBJECT_PRONOUNS_BY_PERSON: dict[str, list[str]] = {
    "1s": ["je"],
    "2s": ["tu"],
    "3s": ["il", "elle", "on"],
    "1p": ["nous"],
    "2p": ["vous"],
    "3p": ["ils", "elles"],
}


def get_subject_pronouns_by_person() -> dict[str, list[str]]:
    """Return subject pronouns grouped by grammatical person slot."""
    return _SUBJECT_PRONOUNS_BY_PERSON
