"""Maltese grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "mt"
LANGUAGE_NAME = "Maltese"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "maltese_noun_forms",
    "schema_name": "MalteseNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "maltese_verb_conjugations",
    "schema_name": "MalteseVerbConjugations",
}
