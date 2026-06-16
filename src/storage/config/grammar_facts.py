"""Compatibility exports for grammar fact release configuration."""

from storage.config.grammar_fact_registry import (
    RELEASE_GRAMMAR_FACT_PREFIXES,
    RELEASE_GRAMMAR_FACT_TYPES,
    get_release_grammar_fact_languages,
    is_release_grammar_fact_type,
)

__all__ = [
    "RELEASE_GRAMMAR_FACT_PREFIXES",
    "RELEASE_GRAMMAR_FACT_TYPES",
    "get_release_grammar_fact_languages",
    "is_release_grammar_fact_type",
]
