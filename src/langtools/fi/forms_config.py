"""Finnish grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "fi"
LANGUAGE_NAME = "Finnish"

CASES: List[str] = [
    "nominative",
    "genitive",
    "partitive",
    "inessive",
    "elative",
    "illative",
    "adessive",
    "ablative",
    "allative",
    "essive",
    "translative",
    "abessive",
    "instructive",
    "comitative",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "finnish_noun_forms",
    "schema_name": "FinnishNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "finnish_verb_conjugations",
    "schema_name": "FinnishVerbConjugations",
}

ADVERB_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "finnish_adverb_forms",
    "schema_name": "FinnishAdverbForms",
}
