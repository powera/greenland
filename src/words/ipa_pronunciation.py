#!/usr/bin/python3

"""Backward-compatible exports for shared IPA generation helpers."""

from ipa.generation import (
    IPA_PRONUNCIATION_JSON_SCHEMA,
    build_ipa_pronunciation_prompt,
    generate_ipa_pronunciation,
    query_ipa_pronunciation,
)

__all__ = [
    "IPA_PRONUNCIATION_JSON_SCHEMA",
    "build_ipa_pronunciation_prompt",
    "generate_ipa_pronunciation",
    "query_ipa_pronunciation",
]
