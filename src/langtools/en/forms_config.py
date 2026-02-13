"""English grammatical structure — single source of truth."""

from typing import Any, Dict, List

LANGUAGE_CODE = "en"
LANGUAGE_NAME = "English"

_PERSONS: List[str] = ["1s", "2s", "3s", "1p", "2p", "3p"]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "english_noun_forms",
    "schema_name": "EnglishNounForms",
    "is_source_language": True,
    "word_variable": "noun",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": [
        *(f"{person}_{tense}" for tense in ["present", "past", "future"] for person in _PERSONS),
        "2s_imp",
        "2p_imp",
    ],
    "query_type": "english_verb_conjugations",
    "schema_name": "EnglishVerbConjugations",
    "is_source_language": True,
    "word_variable": "verb",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "english_adjective_forms",
    "schema_name": "EnglishAdjectiveForms",
    "is_source_language": True,
    "word_variable": "adjective",
}

ADVERB_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "english_adverb_forms",
    "schema_name": "EnglishAdverbForms",
    "is_source_language": True,
    "word_variable": "adverb",
}
