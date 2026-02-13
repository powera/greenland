"""Portuguese grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "pt"
LANGUAGE_NAME = "Portuguese"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "portuguese_noun_forms",
    "schema_name": "PortugueseNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "portuguese_verb_conjugations",
    "schema_name": "PortugueseVerbConjugations",
}
