"""French language tools.

This module provides French-specific parsing for Wiktionary data,
including noun forms, verb conjugations, adjective agreement forms,
and adverb forms.

Example usage:
    from langtools.fr.wiktionary import FrenchParser

    parser = FrenchParser()
    noun_forms, success = parser.get_noun_declensions("chien")
    if success:
        print(noun_forms.forms)
        print(f"Gender: {noun_forms.gender}")

Or using convenience functions:
    from langtools.fr.wiktionary import get_french_noun_forms

    forms, success = get_french_noun_forms("chien")
"""

from langtools.fr.types import (
    AdjectiveDeclension,
    AdverbForms,
    FrenchGender,
    NounDeclension,
    VerbConjugation,
)
from langtools.fr.utils import (
    clean_form,
    detect_gender_from_article,
    extract_article,
    is_elided_form,
    normalize_french_text,
)
from langtools.fr.wiktionary import (
    FrenchParser,
    get_french_adjective_forms,
    get_french_adverb_forms,
    get_french_noun_forms,
    get_french_verb_forms,
)

__all__ = [
    # Parser
    "FrenchParser",
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "FrenchGender",
    "NounDeclension",
    "VerbConjugation",
    # Convenience functions
    "get_french_adjective_forms",
    "get_french_adverb_forms",
    "get_french_noun_forms",
    "get_french_verb_forms",
    # Utilities
    "clean_form",
    "detect_gender_from_article",
    "extract_article",
    "is_elided_form",
    "normalize_french_text",
]
