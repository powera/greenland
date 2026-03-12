"""Subject-pronoun data for lt."""

from __future__ import annotations


_SUBJECT_PRONOUNS_BY_PERSON: dict[str, list[str]] = {
    "1s": ["aš"],
    "2s": ["tu"],
    "3s": ["jis", "ji"],
    "1p": ["mes"],
    "2p": ["jūs"],
    "3p": ["jie", "jos"],
}


def get_subject_pronouns_by_person() -> dict[str, list[str]]:
    """Return subject pronouns grouped by grammatical person slot."""
    return _SUBJECT_PRONOUNS_BY_PERSON
