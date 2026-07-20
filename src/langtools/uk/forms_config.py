"""Ukrainian grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "uk"
LANGUAGE_NAME = "Ukrainian"

CASES: List[str] = [
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "locative",
    "vocative",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "ukrainian_noun_declensions",
    "schema_name": "UkrainianNounDeclensions",
    "extra_schema": {
        "number_type": (
            "string",
            "The number type of this noun",
            ["regular", "plurale_tantum", "singulare_tantum"],
        ),
    },
}

VERB_CONFIG: Dict[str, Any] = {
    # TODO: add "infinitive" (citation form) to this verb config; see en/forms_config.py
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "ukrainian_verb_conjugations",
    "schema_name": "UkrainianVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "case_number_gender",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "genders": ["m", "f"],
    "query_type": "ukrainian_adjective_declensions",
    "schema_name": "UkrainianAdjectiveDeclensions",
}

ADVERB_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "ukrainian_adverb_forms",
    "schema_name": "UkrainianAdverbForms",
}
