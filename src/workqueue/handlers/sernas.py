"""Backward-compatible re-exports for legacy synonym handler imports.

The real implementation lives in :mod:`words.synonyms`. New code should
import from there directly.
"""

from __future__ import annotations

from words.synonyms import (
    SYNONYM_FORM_MAP,
    generate_synonyms_for_lemma,
    normalize_generated_forms,
    query_synonyms_from_llm,
    record_synonym_processing_metadata,
    store_synonym_forms,
)

__all__ = [
    "SYNONYM_FORM_MAP",
    "generate_synonyms_for_lemma",
    "normalize_generated_forms",
    "query_synonyms_from_llm",
    "record_synonym_processing_metadata",
    "store_synonym_forms",
]
