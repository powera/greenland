"""Greek grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "el"
LANGUAGE_NAME = "Greek"

CASES: List[str] = [
    "nominative",
    "genitive",
    "accusative",
    "vocative",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "greek_noun_forms",
    "schema_name": "GreekNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    # TODO: add "infinitive" (citation form) to this verb config; see en/forms_config.py
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "greek_verb_conjugations",
    "schema_name": "GreekVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["singular_m", "singular_f", "singular_n", "plural_m", "plural_f", "plural_n"],
    "query_type": "greek_adjective_forms",
    "schema_name": "GreekAdjectiveForms",
}
