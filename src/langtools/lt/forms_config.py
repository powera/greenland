"""Lithuanian grammatical structure — single source of truth."""

from typing import Any, Dict, List

LANGUAGE_CODE = "lt"
LANGUAGE_NAME = "Lithuanian"

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
    "query_type": "lithuanian_noun_declensions",
    "schema_name": "LithuanianNounDeclensions",
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
    "query_type": "lithuanian_verb_conjugations",
    "schema_name": "LithuanianVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "case_number_gender",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "genders": ["m", "f"],
    "query_type": "lithuanian_adjective_declensions",
    "schema_name": "LithuanianAdjectiveDeclensions",
}

ADVERB_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "lithuanian_adverb_forms",
    "schema_name": "LithuanianAdverbForms",
}
