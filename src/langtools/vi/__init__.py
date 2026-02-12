"""Vietnamese language tools (word forms).

This module provides Vietnamese-specific type definitions for linguistic forms.

Vietnamese is an isolating (analytic) language with no inflectional
morphology, so each part of speech has only a single base form.

Example usage:
    from langtools.vi.types import NounDeclension, VerbForms
"""

from langtools.vi.types import (
    NounDeclension,
    VerbForms,
)

__all__ = [
    # Types
    "NounDeclension",
    "VerbForms",
]
