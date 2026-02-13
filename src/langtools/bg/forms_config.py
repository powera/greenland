"""Bulgarian grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "bg"
LANGUAGE_NAME = "Bulgarian"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "bulgarian_noun_forms",
    "schema_name": "BulgarianNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "bulgarian_verb_conjugations",
    "schema_name": "BulgarianVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["singular_m", "singular_f", "singular_n", "plural"],
    "query_type": "bulgarian_adjective_forms",
    "schema_name": "BulgarianAdjectiveForms",
}
