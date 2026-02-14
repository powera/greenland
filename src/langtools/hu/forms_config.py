"""Hungarian grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "hu"
LANGUAGE_NAME = "Hungarian"

CASES: List[str] = [
    "nominative",
    "accusative",
    "dative",
    "instrumental",
    "causal_final",
    "translative",
    "terminative",
    "essive_formal",
    "inessive",
    "superessive",
    "adessive",
    "sublative",
    "delative",
    "elative",
    "illative",
    "allative",
    "ablative",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "hungarian_noun_forms",
    "schema_name": "HungarianNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "hungarian_verb_conjugations",
    "schema_name": "HungarianVerbConjugations",
}
