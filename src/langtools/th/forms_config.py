"""Thai grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "th"
LANGUAGE_NAME = "Thai"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "thai_noun_forms",
    "schema_name": "ThaiNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "thai_verb_forms",
    "schema_name": "ThaiVerbForms",
}
