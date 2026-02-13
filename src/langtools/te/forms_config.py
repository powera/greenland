"""Telugu grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "te"
LANGUAGE_NAME = "Telugu"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "telugu_noun_forms",
    "schema_name": "TeluguNounForms",
}

# Telugu verbs conjugate by person, number, and gender (in 3rd person).
# Standard 6-person schema.
VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "telugu_verb_conjugations",
    "schema_name": "TeluguVerbConjugations",
}
