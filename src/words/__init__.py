#!/usr/bin/python3

"""Shared word-level generation helpers used by benchmarks and app flows."""

from words.synonyms import build_synonyms_prompt, query_synonyms
from words.translation import (
    build_multi_target_translation_prompt,
    build_single_target_translation_prompt,
    query_multi_word_translation,
    query_single_word_translation,
)
from words.verb_forms import build_verb_forms_prompt, query_verb_forms

__all__ = [
    "build_synonyms_prompt",
    "query_synonyms",
    "build_single_target_translation_prompt",
    "build_multi_target_translation_prompt",
    "query_single_word_translation",
    "query_multi_word_translation",
    "build_verb_forms_prompt",
    "query_verb_forms",
]
