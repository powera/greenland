"""Estonian grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "et"
LANGUAGE_NAME = "Estonian"

CASES: List[str] = [
    "nominative",
    "genitive",
    "partitive",
    "illative",
    "inessive",
    "elative",
    "allative",
    "adessive",
    "ablative",
    "translative",
    "terminative",
    "essive",
    "abessive",
    "comitative",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "estonian_noun_declensions",
    "schema_name": "EstonianNounDeclensions",
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
    "query_type": "estonian_verb_conjugations",
    "schema_name": "EstonianVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "estonian_adjective_declensions",
    "schema_name": "EstonianAdjectiveDeclensions",
}

ADVERB_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "estonian_adverb_forms",
    "schema_name": "EstonianAdverbForms",
}
