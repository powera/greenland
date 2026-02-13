"""Bengali language tools.

This module provides Bengali-specific type definitions for linguistic forms,
including noun declensions, verb conjugations, and adjective forms.

Example usage:
    from langtools.bn.types import NounDeclension, VerbConjugation
"""

from langtools.bn.types import (
    AdjectiveForms,
    NounDeclension,
    VerbConjugation,
)
from langtools.bn.utils import (
    clean_form,
    is_bengali_script,
    normalize_bengali_text,
    remove_nukta_marks,
)

__all__ = [
    # Types
    "AdjectiveForms",
    "NounDeclension",
    "VerbConjugation",
    # Utilities
    "clean_form",
    "is_bengali_script",
    "normalize_bengali_text",
    "remove_nukta_marks",
]
