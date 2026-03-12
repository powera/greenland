"""Subject-pronoun data for nl."""

from __future__ import annotations


_SUBJECT_PRONOUNS_BY_PERSON: dict[str, list[str]] = {
    "1s": ["ik"],
    "2s": ["jij"],
    "3s": ["hij", "zij", "het"],
    "1p": ["wij"],
    "2p": ["jullie"],
    "3p": ["zij"],
}


def get_subject_pronouns_by_person() -> dict[str, list[str]]:
    """Return subject pronouns grouped by grammatical person slot."""
    return _SUBJECT_PRONOUNS_BY_PERSON
