"""Swahili grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "sw"
LANGUAGE_NAME = "Swahili"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "swahili_noun_forms",
    "schema_name": "SwahiliNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "swahili_verb_forms",
    "schema_name": "SwahiliVerbForms",
}
