"""Thai language tools.

This module provides Thai-specific type definitions for linguistic forms,
including noun forms, verb forms, adjective forms, and adverb forms.

Example usage:
    from langtools.th.types import NounDeclension, VerbConjugation
"""

from langtools.th.types import (
    AdjectiveForms,
    AdverbForms,
    NounDeclension,
    VerbConjugation,
)
from langtools.th.utils import (
    clean_form,
    contains_thai,
    normalize_thai_text,
    thai_digits_to_arabic,
)

__all__ = [
    # Types
    "AdjectiveForms",
    "AdverbForms",
    "NounDeclension",
    "VerbConjugation",
    # Utilities
    "clean_form",
    "contains_thai",
    "normalize_thai_text",
    "thai_digits_to_arabic",
]
