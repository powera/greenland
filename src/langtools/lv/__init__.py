"""Latvian language tools.

This module provides Latvian-specific type definitions for linguistic forms,
including noun declensions, verb conjugations, adjective declensions,
and adverb forms.

Example usage:
    from langtools.lv.types import NounDeclension, VerbConjugation
"""

from langtools.lv.types import (
    AdjectiveDeclension,
    AdverbForms,
    LatvianGender,
    NounDeclension,
    VerbConjugation,
)
from langtools.lv.utils import (
    clean_form,
    normalize_latvian_text,
    remove_long_mark_stress,
)

__all__ = [
    # Types
    "AdjectiveDeclension",
    "AdverbForms",
    "LatvianGender",
    "NounDeclension",
    "VerbConjugation",
    # Utilities
    "clean_form",
    "normalize_latvian_text",
    "remove_long_mark_stress",
]
