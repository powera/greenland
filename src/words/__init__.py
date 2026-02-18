#!/usr/bin/python3

"""Shared word-level generation helpers used by benchmarks and app flows."""

from words.synonyms import build_synonyms_prompt, query_synonyms
from words.verb_forms import build_verb_forms_prompt, query_verb_forms

__all__ = [
    "build_synonyms_prompt",
    "query_synonyms",
    "build_verb_forms_prompt",
    "query_verb_forms",
]
