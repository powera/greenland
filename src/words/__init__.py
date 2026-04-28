#!/usr/bin/python3

"""Shared word-level generation helpers used by benchmarks and app flows."""

from words.synonyms import (
    SYNONYM_FORM_MAP,
    SYNONYMS_JSON_SCHEMA,
    build_synonyms_prompt,
    generate_synonyms_for_lemma,
    normalize_generated_forms,
    query_synonyms,
    query_synonyms_from_llm,
    record_synonym_processing_metadata,
    store_synonym_forms,
)
from words.word2vec import rebuild_embeddings, refresh_lemma_embedding, suggest_similar_lemmas
from words.translation import (
    build_multi_target_translation_prompt,
    build_single_target_translation_prompt,
    query_multi_word_translation,
    query_single_word_translation,
)
from words.verb_forms import build_verb_forms_prompt, query_verb_forms
from words.ipa_pronunciation import (
    build_ipa_pronunciation_prompt,
    generate_ipa_pronunciation,
    query_ipa_pronunciation,
)

__all__ = [
    "SYNONYM_FORM_MAP",
    "SYNONYMS_JSON_SCHEMA",
    "build_synonyms_prompt",
    "generate_synonyms_for_lemma",
    "normalize_generated_forms",
    "query_synonyms",
    "query_synonyms_from_llm",
    "record_synonym_processing_metadata",
    "store_synonym_forms",
    "refresh_lemma_embedding",
    "rebuild_embeddings",
    "suggest_similar_lemmas",
    "build_single_target_translation_prompt",
    "build_multi_target_translation_prompt",
    "query_single_word_translation",
    "query_multi_word_translation",
    "build_verb_forms_prompt",
    "query_verb_forms",
    "build_ipa_pronunciation_prompt",
    "generate_ipa_pronunciation",
    "query_ipa_pronunciation",
]
