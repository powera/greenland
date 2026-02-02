"""Lithuanian language tools.

This module provides Lithuanian-specific parsing for Wiktionary data,
including noun declensions, verb conjugations, adjective declensions,
and adverb forms.

Example usage:
    from langtools.lt.wiktionary import LithuanianParser

    parser = LithuanianParser()
    declensions, success = parser.get_noun_declensions("vilkas")
    if success:
        print(declensions.forms)

Or using convenience functions:
    from langtools.lt.wiktionary import get_lithuanian_noun_forms

    forms, success = get_lithuanian_noun_forms("vilkas")
"""

from langtools.lt.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    VerbConjugation,
)
from langtools.lt.utils import (
    clean_form,
    normalize_lithuanian_text,
    remove_stress_marks,
)
from langtools.lt.wiktionary import (
    LithuanianParser,
    get_lithuanian_adjective_forms,
    get_lithuanian_adverb_forms,
    get_lithuanian_noun_forms,
    get_lithuanian_verb_forms,
)

__all__ = [
    # Parser
    "LithuanianParser",
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "NounDeclension",
    "VerbConjugation",
    # Convenience functions
    "get_lithuanian_adjective_forms",
    "get_lithuanian_adverb_forms",
    "get_lithuanian_noun_forms",
    "get_lithuanian_verb_forms",
    # Utilities
    "clean_form",
    "normalize_lithuanian_text",
    "remove_stress_marks",
]
