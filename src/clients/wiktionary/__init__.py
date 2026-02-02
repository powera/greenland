"""
Wiktionary client for fetching linguistic data.

This module provides access to Wiktionary's API for fetching grammatical forms
of words in various languages. Currently focused on Lithuanian support.

Example usage:
    from clients.wiktionary import WiktionaryClient, LithuanianParser

    # Using the parser directly
    parser = LithuanianParser()
    declensions, success = parser.get_noun_declensions("vilkas")
    if success:
        print(declensions.forms)

    # Using convenience functions
    from clients.wiktionary import get_lithuanian_noun_forms
    forms, success = get_lithuanian_noun_forms("vilkas")
"""

from clients.wiktionary.client import WiktionaryClient
from clients.wiktionary.lithuanian import (
    LithuanianParser,
    get_lithuanian_adjective_forms,
    get_lithuanian_adverb_forms,
    get_lithuanian_noun_forms,
    get_lithuanian_verb_forms,
)
from clients.wiktionary.types import (
    AdjectiveDeclension,
    AdverbForms,
    FormResult,
    NounDeclension,
    NounNumberType,
    PartOfSpeech,
    VerbConjugation,
    WiktionaryResult,
)
from clients.wiktionary.utils import (
    clean_form,
    extract_alternative_forms,
    extract_primary_form,
    is_placeholder_text,
    normalize_lithuanian_text,
    remove_stress_marks,
)

__all__ = [
    # Client classes
    "WiktionaryClient",
    "LithuanianParser",
    # Type classes
    "AdjectiveDeclension",
    "AdverbForms",
    "FormResult",
    "NounDeclension",
    "NounNumberType",
    "PartOfSpeech",
    "VerbConjugation",
    "WiktionaryResult",
    # Convenience functions
    "get_lithuanian_noun_forms",
    "get_lithuanian_verb_forms",
    "get_lithuanian_adjective_forms",
    "get_lithuanian_adverb_forms",
    # Utility functions
    "clean_form",
    "extract_alternative_forms",
    "extract_primary_form",
    "is_placeholder_text",
    "normalize_lithuanian_text",
    "remove_stress_marks",
]
