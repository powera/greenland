"""Shona grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "sn"
LANGUAGE_NAME = "Shona"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "shona_noun_forms",
    "schema_name": "ShonaNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "shona_verb_forms",
    "schema_name": "ShonaVerbForms",
}
