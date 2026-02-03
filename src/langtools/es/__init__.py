"""Spanish language tools.

This module provides Spanish-specific parsing for Wiktionary data,
including noun forms, verb conjugations, adjective forms,
and adverb forms.

Example usage:
    from langtools.es.wiktionary import SpanishParser

    parser = SpanishParser()
    forms, success = parser.get_noun_declensions("perro")
    if success:
        print(forms.forms)
        print(f"Gender: {forms.gender}")

Or using convenience functions:
    from langtools.es.wiktionary import get_spanish_noun_forms

    forms, success = get_spanish_noun_forms("perro")
"""

from langtools.es.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    SpanishGender,
    VerbConjugation,
)
from langtools.es.utils import (
    clean_form,
    detect_gender_from_article,
    detect_gender_from_word,
    extract_article,
    normalize_spanish_text,
)
from langtools.es.wiktionary import (
    SpanishParser,
    get_spanish_adjective_forms,
    get_spanish_adverb_forms,
    get_spanish_noun_forms,
    get_spanish_verb_forms,
)

__all__ = [
    # Parser
    "SpanishParser",
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "NounDeclension",
    "SpanishGender",
    "VerbConjugation",
    # Convenience functions
    "get_spanish_adjective_forms",
    "get_spanish_adverb_forms",
    "get_spanish_noun_forms",
    "get_spanish_verb_forms",
    # Utilities
    "clean_form",
    "detect_gender_from_article",
    "detect_gender_from_word",
    "extract_article",
    "normalize_spanish_text",
]
