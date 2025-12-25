#!/usr/bin/env python3

"""
Trakaido Wordlists - Lithuanian language wordlists for language learning applications.

This package provides comprehensive Lithuanian wordlists including nouns, verbs, phrases,
and utility functions for language learning applications.
"""

__version__ = "1.0.0"
__author__ = "Trakaido Project"
__email__ = "contact@trakaido.com"

# Import all wordlists and utility functions
from .wordlists import (
    all_words,
    get_all_word_pairs_flat,
)

from .nouns import (
    nouns_one,
    nouns_two, 
    nouns_three,
    nouns_four,
    common_words
)

from .verbs import (
    verbs_present,
    verbs_past,
    verbs_new
)

from .phrases import (
    phrases_one
)

# Make commonly used items available at package level
__all__ = [
    # Main data structures
    'all_words',
    'nouns_one',
    'nouns_two', 
    'nouns_three',
    'nouns_four',
    'common_words',
    'verbs_present',
    'verbs_past',
    'verbs_new',
    'phrases_one',
    
    # Utility functions
    'get_all_word_pairs_flat',
    'check_for_duplicates',
    'find_missing_words',
]