"""Portuguese grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "pt"
LANGUAGE_NAME = "Portuguese"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "portuguese_noun_forms",
    "schema_name": "PortugueseNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "portuguese_verb_conjugations",
    "schema_name": "PortugueseVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["singular_m", "singular_f", "plural_m", "plural_f"],
    "query_type": "portuguese_adjective_forms",
    "schema_name": "PortugueseAdjectiveForms",
}

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADJ_PT_PLURAL_F": "adjective/pt_plural_f",
    "ADJ_PT_PLURAL_M": "adjective/pt_plural_m",
    "ADJ_PT_SINGULAR_F": "adjective/pt_singular_f",
    "ADJ_PT_SINGULAR_M": "adjective/pt_singular_m",
    "ADVERB_PT_BASE": "adverb/pt_base",
    "ARTICLE_PT_FEMININE_SINGULAR": "article/pt_feminine_singular",
    "ARTICLE_PT_MASCULINE_SINGULAR": "article/pt_masculine_singular",
    "ARTICLE_PT_PLURAL": "article/pt_plural",
    "NUMERAL_PT_CARDINAL_F": "numeral/pt_cardinal_f",
    "NUMERAL_PT_CARDINAL_M": "numeral/pt_cardinal_m",
    "NUMERAL_PT_ORDINAL_F": "numeral/pt_ordinal_f",
    "NUMERAL_PT_ORDINAL_M": "numeral/pt_ordinal_m",
    "PRONOUN_PT_OBJECTIVE": "pronoun/pt_objective",
    "PRONOUN_PT_POSSESSIVE": "pronoun/pt_possessive",
    "PRONOUN_PT_REFLEXIVE": "pronoun/pt_reflexive",
    "PRONOUN_PT_SUBJECTIVE": "pronoun/pt_subjective",
    "VERB_PT_3P_F_FUTURE": "verb/pt_3p-f_future",
    "VERB_PT_3P_F_PAST": "verb/pt_3p-f_past",
    "VERB_PT_3P_F_PRESENT": "verb/pt_3p-f_present",
    "VERB_PT_3P_M_FUTURE": "verb/pt_3p-m_future",
    "VERB_PT_3P_M_PAST": "verb/pt_3p-m_past",
    "VERB_PT_3P_M_PRESENT": "verb/pt_3p-m_present",
    "VERB_PT_3S_F_FUTURE": "verb/pt_3s-f_future",
    "VERB_PT_3S_F_PAST": "verb/pt_3s-f_past",
    "VERB_PT_3S_F_PRESENT": "verb/pt_3s-f_present",
    "VERB_PT_3S_M_FUTURE": "verb/pt_3s-m_future",
    "VERB_PT_3S_M_PAST": "verb/pt_3s-m_past",
    "VERB_PT_3S_M_PRESENT": "verb/pt_3s-m_present",
}
