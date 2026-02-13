"""Kannada grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "kn"
LANGUAGE_NAME = "Kannada"

CASES: List[str] = [
    "nominative",
    "accusative",
    "instrumental",
    "dative",
    "ablative",
    "genitive",
    "locative",
    "vocative",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "kannada_noun_declensions",
    "schema_name": "KannadaNounDeclensions",
    "extra_schema": {
        "number_type": (
            "string",
            "The number type of this noun",
            ["regular", "plurale_tantum", "singulare_tantum"],
        ),
    },
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "kannada_verb_conjugations",
    "schema_name": "KannadaVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "kannada_adjective_forms",
    "schema_name": "KannadaAdjectiveForms",
}

ADVERB_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "kannada_adverb_forms",
    "schema_name": "KannadaAdverbForms",
}
