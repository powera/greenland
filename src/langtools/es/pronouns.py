"""Subject-pronoun data for es."""

from __future__ import annotations

from langtools.es.conjugation import uses_ustedes
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
    ],
    "3p": [
        {"text": "ellos", "variation": "gender", "note": "masculine or mixed group"},
        {"text": "ellas", "variation": "gender", "note": "all-feminine group"},
    ],
}


# Latin American Spanish has no vosotros: "ustedes" fills the second person
# plural, taking the same verb form as ellos/ellas.  Listing it here rather
# than beside vosotros keeps each pronoun with the form it actually governs.
_USTEDES_2P: list[PronounVariant] = [
    {
        "text": "ustedes",
        "variation": "regional",
        "note": "Latin American second-person plural, formal and informal alike",
    },
]


def get_subject_pronoun_variants_by_person(
    language_code: str = "es",
) -> dict[str, list[PronounVariant]]:
    """Return subject pronoun variants grouped by grammatical person slot."""
    if not uses_ustedes(language_code):
        return _SUBJECT_PRONOUN_VARIANTS_BY_PERSON
    variants = dict(_SUBJECT_PRONOUN_VARIANTS_BY_PERSON)
    variants["2p"] = _USTEDES_2P
    return variants
