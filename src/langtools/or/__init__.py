"""Odia language tools.

This module provides Odia-specific type definitions for linguistic forms,
including noun forms and verb forms.

Example usage:
    from langtools.or.types import NounDeclension, VerbConjugation
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
