"""German language tools.

This module provides German-specific parsing for Wiktionary data,
including noun declensions, verb conjugations, adjective declensions,
and adverb forms.

Example usage:
    from langtools.de.wiktionary import GermanParser

    parser = GermanParser()
    declensions, success = parser.get_noun_declensions("Hund")
    if success:
        print(declensions.forms)
        print(f"Gender: {declensions.gender}")

Or using convenience functions:
    from langtools.de.wiktionary import get_german_noun_forms

    forms, success = get_german_noun_forms("Hund")
"""

from langtools.de.types import (
    AdjectiveDeclension,
    AdverbForms,
    GermanGender,
    NounDeclension,
    VerbConjugation,
)
from langtools.de.utils import (
    clean_form,
    detect_gender_from_article,
    extract_article,
    normalize_german_text,
)
from langtools.de.wiktionary import (
    GermanParser,
    get_german_adjective_forms,
    get_german_adverb_forms,
    get_german_noun_forms,
    get_german_verb_forms,
)

__all__ = [
    # Parser
    "GermanParser",
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "GermanGender",
    "NounDeclension",
    "VerbConjugation",
    # Convenience functions
    "get_german_adjective_forms",
    "get_german_adverb_forms",
    "get_german_noun_forms",
    "get_german_verb_forms",
    # Utilities
    "clean_form",
    "detect_gender_from_article",
    "extract_article",
    "normalize_german_text",
]
