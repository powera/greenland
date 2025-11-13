#!/usr/bin/env python3
"""
Bebras - Sentence-Word Link Management Agent

This agent manages the relationship between sentences and the vocabulary words
they contain. It uses LLM analysis to extract key words, resolve ambiguities,
and create proper database links for language learning applications.

"Bebras" means "beaver" in Lithuanian - industrious builder of connections!
"""

from .agent import BebrasAgent
from .disambiguation import disambiguate_lemma, find_best_lemma_match
from .translation import ensure_translations

__all__ = [
    'BebrasAgent',
    'disambiguate_lemma',
    'find_best_lemma_match',
    'ensure_translations'
]
