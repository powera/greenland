"""Spanish grammatical structure — single source of truth."""

from typing import Any, Dict

LANGUAGE_CODE = "es"
LANGUAGE_NAME = "Spanish"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "spanish_noun_forms",
    "schema_name": "SpanishNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "spanish_verb_conjugations",
    "schema_name": "SpanishVerbConjugations",
}
