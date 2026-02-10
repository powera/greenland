"""Polish language tools.

This module provides Polish-specific type definitions for linguistic forms,
including noun declensions, verb conjugations, and adjective forms.

Example usage:
    from langtools.pl.types import NounDeclension, VerbConjugation
"""

from langtools.pl.types import (
    AdjectiveDeclension,
    NounDeclension,
    PolishGender,
    VerbConjugation,
)

__all__ = [
    # Types
    "AdjectiveDeclension",
    "NounDeclension",
    "PolishGender",
    "VerbConjugation",
]
