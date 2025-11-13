"""
Dramblys Agent - Word Validation

This module contains logic for validating whether words should be considered
for import (e.g., checking stopwords, valid characters, etc.).
"""

import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import util.stopwords


def is_valid_word(word: str) -> bool:
    """
    Check if a word is valid (not a stopword, has only letters, etc.).

    Args:
        word: Word to check

    Returns:
        True if valid
    """
    word_lower = word.lower()

    # Skip stopwords - check all categories
    if word_lower in util.stopwords.all_stopwords:
        return False

    # Also check common words that shouldn't be priorities
    if word_lower in util.stopwords.COMMON_VERBS:
        return False
    if word_lower in util.stopwords.COMMON_NOUNS:
        return False
    if word_lower in util.stopwords.COMMON_ADVERBS:
        return False
    if word_lower in util.stopwords.MISC_WORDS:
        return False

    # Check contractions
    if word in util.stopwords.CONTRACTIONS:
        return False

    # Must contain at least one letter
    if not any(c.isalpha() for c in word):
        return False

    # Skip very short words (likely abbreviations or noise)
    if len(word) < 2:
        return False

    # Skip words with numbers
    if any(c.isdigit() for c in word):
        return False

    # Skip words with special characters (except hyphens and apostrophes)
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'-")
    if not all(c in allowed_chars for c in word):
        return False

    return True
