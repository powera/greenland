#!/usr/bin/python3

"""Shared word-level generation helpers used by benchmarks and app flows."""

from words.synonyms import build_synonyms_prompt
from words.verb_forms import build_verb_forms_prompt

__all__ = ["build_synonyms_prompt", "build_verb_forms_prompt"]

