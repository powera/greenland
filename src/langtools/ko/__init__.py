"""Korean language tools (hangul decomposition, word forms).

This module provides Korean-specific type definitions for linguistic forms
as well as hangul decomposition for sort keys.

Example usage:
    from langtools.ko.types import NounDeclension, VerbConjugation
"""

from langtools.ko.types import (
    NounDeclension,
    VerbConjugation,
)

__all__ = [
    # Types
    "NounDeclension",
    "VerbConjugation",
]
