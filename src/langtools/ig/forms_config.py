"""Igbo grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "ig"
LANGUAGE_NAME = "Igbo"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "igbo_noun_forms",
    "schema_name": "IgboNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "igbo_verb_forms",
    "schema_name": "IgboVerbForms",
}
