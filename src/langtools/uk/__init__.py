"""Ukrainian language tools.

This module provides Ukrainian-specific type definitions for linguistic forms,
including noun declensions, verb conjugations, adjective declensions,
and adverb forms.

Example usage:
    from langtools.uk.types import NounDeclension, VerbConjugation
"""

from langtools.uk.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    UkrainianGender,
    VerbConjugation,
)
from langtools.uk.utils import (
    clean_form,
    normalize_ukrainian_text,
    remove_stress_marks,
)

__all__ = [
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "NounDeclension",
    "UkrainianGender",
    "VerbConjugation",
    # Utilities
    "clean_form",
    "normalize_ukrainian_text",
    "remove_stress_marks",
]
