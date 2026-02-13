"""Somali grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "so"
LANGUAGE_NAME = "Somali"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "somali_noun_forms",
    "schema_name": "SomaliNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "somali_verb_forms",
    "schema_name": "SomaliVerbForms",
}
