"""Czech grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "cs"
LANGUAGE_NAME = "Czech"

CASES: List[str] = [
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "vocative",
    "locative",
    "instrumental",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "czech_noun_forms",
    "schema_name": "CzechNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    # TODO: add "infinitive" (citation form) to this verb config; see en/forms_config.py
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "czech_verb_conjugations",
    "schema_name": "CzechVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["singular_m", "singular_f", "plural_m", "plural_f"],
    "query_type": "czech_adjective_forms",
    "schema_name": "CzechAdjectiveForms",
}
