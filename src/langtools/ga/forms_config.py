"""Irish grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "ga"
LANGUAGE_NAME = "Irish"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "irish_noun_forms",
    "schema_name": "IrishNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    # TODO: add "infinitive" (citation form) to this verb config; see en/forms_config.py
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "irish_verb_conjugations",
    "schema_name": "IrishVerbConjugations",
}
