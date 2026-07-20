"""Filipino (Tagalog) language tools.

This module provides Filipino-specific type definitions for linguistic forms,
including noun forms and verb forms.

Example usage:
    from langtools.tl.types import NounDeclension, VerbConjugation

Status: not fully enabled. This language is a Pattern B language in
langtools/form_registry.py and has no forms_config.py yet, so it has no
FORM_SPECS entry and importing langtools.tl.llm_forms raises KeyError.
Writing forms_config.py enables LLM form generation for it.
"""

from langtools.tl.types import (
    NounDeclension,
    VerbConjugation,
)

__all__ = [
    # Types
    "NounDeclension",
    "VerbConjugation",
]
