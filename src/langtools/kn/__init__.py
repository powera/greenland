"""Kannada language tools.

This module provides Kannada-specific type definitions for linguistic forms,
including noun declensions, verb conjugations, adjective forms,
and adverb forms.

Example usage:
    from langtools.kn.types import NounDeclension, VerbConjugation
"""

from langtools.kn.types import (
    AdjectiveForms,
    AdverbForms,
    KannadaGender,
    NounDeclension,
    VerbConjugation,
)
from langtools.kn.utils import (
    clean_form,
    normalize_kannada_text,
    remove_vowel_signs,
)

__all__ = [
    # Types
    "AdjectiveForms",
    "AdverbForms",
    "KannadaGender",
    "NounDeclension",
    "VerbConjugation",
    # Utilities
    "clean_form",
    "normalize_kannada_text",
    "remove_vowel_signs",
]
