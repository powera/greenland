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
        "infinitive",
        *(f"{person}_{tense}" for tense in ["present", "past", "future"] for person in _PERSONS),
        "2s_imp",
        "2p_imp",
        "present_participle",
        "past_participle",
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

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADVERB_EN_BASE": "adverb/en_base",
    "ARTICLE_EN_BASE": "article/en_base",
    "NUMERAL_EN_CARDINAL": "numeral/en_cardinal",
    "NUMERAL_EN_ORDINAL": "numeral/en_ordinal",
    "PRONOUN_EN_OBJECTIVE": "pronoun/en_objective",
    "PRONOUN_EN_POSSESSIVE": "pronoun/en_possessive",
    "PRONOUN_EN_REFLEXIVE": "pronoun/en_reflexive",
    "PRONOUN_EN_SUBJECTIVE": "pronoun/en_subjective",
}
