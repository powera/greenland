"""Bengali grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "bn"
LANGUAGE_NAME = "Bengali"

# Bengali 4-case system (vibhakti)
CASES: List[str] = [
    "nominative",
    "objective",
    "genitive",
    "locative",
]

# Bengali 5-person system (register-based rather than number-based)
PERSONS: List[str] = ["1", "2int", "2fam", "3", "3hon"]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "bengali_noun_declensions",
    "schema_name": "BengaliNounDeclensions",
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
    "persons": PERSONS,
    "tenses": ["present", "past", "future"],
    "query_type": "bengali_verb_conjugations",
    "schema_name": "BengaliVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "bengali_adjective_forms",
    "schema_name": "BengaliAdjectiveForms",
}
