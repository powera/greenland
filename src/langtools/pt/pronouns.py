"""Subject-pronoun data for pt."""

from __future__ import annotations


_SUBJECT_PRONOUNS_BY_PERSON: dict[str, list[str]] = {
    "1s": ["eu"],
    "2s": ["tu"],
    "3s": ["ele", "ela", "você"],
    "1p": ["nós"],
    "2p": ["vós"],
    "3p": ["eles", "elas", "vocês"],
}


def get_subject_pronouns_by_person() -> dict[str, list[str]]:
    """Return subject pronouns grouped by grammatical person slot."""
    return _SUBJECT_PRONOUNS_BY_PERSON
