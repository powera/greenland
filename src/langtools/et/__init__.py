"""Estonian language tools.

This module provides Estonian-specific type definitions for linguistic forms,
including noun declensions, verb conjugations, adjective declensions,
and adverb forms.

Example usage:
    from langtools.et.types import NounDeclension, VerbConjugation
"""

from langtools.et.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    VerbConjugation,
)
from langtools.et.utils import (
    clean_form,
    normalize_estonian_text,
    remove_stress_marks,
)

__all__ = [
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "NounDeclension",
    "VerbConjugation",
    # Utilities
    "clean_form",
    "normalize_estonian_text",
    "remove_stress_marks",
]
