"""Romanian grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "ro"
LANGUAGE_NAME = "Romanian"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "romanian_noun_forms",
    "schema_name": "RomanianNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "romanian_verb_conjugations",
    "schema_name": "RomanianVerbConjugations",
}
