"""Japanese language tools (romaji, word forms).

This module provides Japanese-specific type definitions for linguistic forms
as well as romaji generation and gojuon ordering utilities.

Example usage:
    from langtools.ja.types import NounDeclension, VerbConjugation
"""

from langtools.ja.script_analysis import (
    JapaneseScriptType,
    classify_japanese_script,
    contains_japanese,
    has_hiragana,
    has_kanji,
    has_katakana,
    kanji_ratio,
)
from langtools.ja.types import (
    NounDeclension,
    VerbConjugation,
)

__all__ = [
    # Types
    "NounDeclension",
    "VerbConjugation",
    # Script analysis (word-level signals)
    "JapaneseScriptType",
    "classify_japanese_script",
    "contains_japanese",
    "has_hiragana",
    "has_kanji",
    "has_katakana",
    "kanji_ratio",
]
