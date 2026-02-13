"""French grammatical structure — single source of truth."""

from typing import Any, Dict, List

LANGUAGE_CODE = "fr"
LANGUAGE_NAME = "French"

_PERSONS: List[str] = ["1s", "2s", "3s", "1p", "2p", "3p"]

VERB_FORMS: List[str] = [
    *(f"{person}_{tense}" for tense in ["present", "impf", "future"] for person in _PERSONS),
    "pc_m",
    "pc_f",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "french_noun_forms",
    "schema_name": "FrenchNounForms",
    "schema_description": "French noun forms with gender",
    "extra_schema": {
        "gender": ("string", "Gender: 'masculine' or 'feminine'"),
    },
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": VERB_FORMS,
    "query_type": "french_verb_conjugations",
    "schema_name": "FrenchVerbConjugations",
}
