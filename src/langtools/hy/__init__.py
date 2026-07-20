"""Armenian language tools.

This module provides Armenian-specific type definitions for linguistic forms,
including noun forms and verb conjugations.

Example usage:
    from langtools.hy.types import NounDeclension, VerbConjugation

Status: not fully enabled. This language is a Pattern B language in
langtools/form_registry.py and has no forms_config.py yet, so it has no
FORM_SPECS entry and importing langtools.hy.llm_forms raises KeyError.
Writing forms_config.py enables LLM form generation for it.
"""

from langtools.hy.types import (
    NounDeclension,
    VerbConjugation,
)

__all__ = [
    # Types
    "NounDeclension",
    "VerbConjugation",
]
