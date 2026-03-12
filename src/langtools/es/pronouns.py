"""Subject-pronoun data for es."""

from __future__ import annotations

from langtools.person_labels import PronounVariant


_SUBJECT_PRONOUN_VARIANTS_BY_PERSON: dict[str, list[PronounVariant]] = {
    "1s": [
        {"text": "yo", "variation": "default", "note": "standard first-person singular"},
    ],
    "2s": [
        {"text": "tú", "variation": "register", "note": "informal singular"},
        {"text": "usted", "variation": "register", "note": "formal singular"},
    ],
    "3s": [
        {"text": "él", "variation": "gender", "note": "masculine"},
        {"text": "ella", "variation": "gender", "note": "feminine"},
    ],
    "1p": [
        {
            "text": "nosotros",
            "variation": "gender",
            "note": "masculine or mixed group",
        },
        {
            "text": "nosotras",
            "variation": "gender",
            "note": "all-feminine group",
        },
    ],
    "2p": [
        {"text": "vosotros", "variation": "regional", "note": "Spain, masculine/mixed"},
        {"text": "vosotras", "variation": "regional", "note": "Spain, all-feminine"},
        {
            "text": "ustedes",
            "variation": "regional",
            "note": "Latin America general form; formal in much of Spain",
        },
    ],
    "3p": [
        {"text": "ellos", "variation": "gender", "note": "masculine or mixed group"},
        {"text": "ellas", "variation": "gender", "note": "all-feminine group"},
    ],
}


def get_subject_pronoun_variants_by_person() -> dict[str, list[PronounVariant]]:
    """Return subject pronoun variants grouped by grammatical person slot."""
    return _SUBJECT_PRONOUN_VARIANTS_BY_PERSON
