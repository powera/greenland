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

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADJ_ES_PLURAL_F": "adjective/es_plural_f",
    "ADJ_ES_PLURAL_M": "adjective/es_plural_m",
    "ADJ_ES_SINGULAR_F": "adjective/es_singular_f",
    "ADJ_ES_SINGULAR_M": "adjective/es_singular_m",
    "ADVERB_ES_BASE": "adverb/es_base",
    "ARTICLE_ES_FEMININE_SINGULAR": "article/es_feminine_singular",
    "ARTICLE_ES_MASCULINE_SINGULAR": "article/es_masculine_singular",
    "ARTICLE_ES_PLURAL": "article/es_plural",
    "NUMERAL_ES_CARDINAL_F": "numeral/es_cardinal_f",
    "NUMERAL_ES_CARDINAL_M": "numeral/es_cardinal_m",
    "NUMERAL_ES_ORDINAL_F": "numeral/es_ordinal_f",
    "NUMERAL_ES_ORDINAL_M": "numeral/es_ordinal_m",
    "PRONOUN_ES_OBJECTIVE": "pronoun/es_objective",
    "PRONOUN_ES_POSSESSIVE": "pronoun/es_possessive",
    "PRONOUN_ES_REFLEXIVE": "pronoun/es_reflexive",
    "PRONOUN_ES_SUBJECTIVE": "pronoun/es_subjective",
    "VERB_ES_3P_F_FUTURE": "verb/es_3p-f_future",
    "VERB_ES_3P_F_PAST": "verb/es_3p-f_past",
    "VERB_ES_3P_F_PRESENT": "verb/es_3p-f_present",
    "VERB_ES_3P_M_FUTURE": "verb/es_3p-m_future",
    "VERB_ES_3P_M_PAST": "verb/es_3p-m_past",
    "VERB_ES_3P_M_PRESENT": "verb/es_3p-m_present",
    "VERB_ES_3S_F_FUTURE": "verb/es_3s-f_future",
    "VERB_ES_3S_F_PAST": "verb/es_3s-f_past",
    "VERB_ES_3S_F_PRESENT": "verb/es_3s-f_present",
    "VERB_ES_3S_M_FUTURE": "verb/es_3s-m_future",
    "VERB_ES_3S_M_PAST": "verb/es_3s-m_past",
    "VERB_ES_3S_M_PRESENT": "verb/es_3s-m_present",
}
