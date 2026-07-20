"""Odia language tools.

This module provides Odia-specific type definitions for linguistic forms,
including noun forms and verb forms.

Example usage:
    from langtools.or.types import NounDeclension, VerbConjugation

Status: not fully enabled. This language is a Pattern B language in
langtools/form_registry.py and has no forms_config.py yet, so it has no
FORM_SPECS entry and importing langtools.or.llm_forms raises KeyError.
Writing forms_config.py enables LLM form generation for it.
"""

from importlib import import_module

_types_module = import_module("langtools.or.types")

NounDeclension = _types_module.NounDeclension
VerbConjugation = _types_module.VerbConjugation

__all__ = [
    # Types
    "NounDeclension",
    "VerbConjugation",
]
