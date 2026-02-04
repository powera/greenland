"""English language tools.

This module provides English-specific parsing for Wiktionary data,
including noun forms, verb conjugations, adjective forms,
and adverb forms.

Example usage:
    from langtools.en.wiktionary import EnglishParser

    parser = EnglishParser()
    forms, success = parser.get_noun_declensions("mouse")
    if success:
        print(forms.forms)  # {'singular': 'mouse', 'plural': 'mice'}

Or using convenience functions:
    from langtools.en.wiktionary import get_english_noun_forms

    forms, success = get_english_noun_forms("mouse")
"""

from langtools.en.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    VerbConjugation,
)
from langtools.en.utils import (
    clean_form,
    generate_3s_present,
    generate_comparative,
    generate_past_tense,
    generate_present_participle,
    generate_regular_plural,
    generate_superlative,
)
from langtools.en.wiktionary import (
    EnglishParser,
    get_english_adjective_forms,
    get_english_adverb_forms,
    get_english_noun_forms,
    get_english_verb_forms,
)

__all__ = [
    # Parser
    "EnglishParser",
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "NounDeclension",
    "VerbConjugation",
    # Convenience functions
    "get_english_adjective_forms",
    "get_english_adverb_forms",
    "get_english_noun_forms",
    "get_english_verb_forms",
    # Utilities
    "clean_form",
    "generate_3s_present",
    "generate_comparative",
    "generate_past_tense",
    "generate_present_participle",
    "generate_regular_plural",
    "generate_superlative",
]
