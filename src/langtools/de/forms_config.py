"""German grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "de"
LANGUAGE_NAME = "German"

CASES: List[str] = ["nominative", "accusative", "dative", "genitive"]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "german_noun_forms",
    "schema_name": "GermanNounDeclensions",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "german_verb_conjugations",
    "schema_name": "GermanVerbConjugations",
}

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADJ_DE_PLURAL_F": "adjective/de_plural_f",
    "ADJ_DE_PLURAL_M": "adjective/de_plural_m",
    "ADJ_DE_SINGULAR_F": "adjective/de_singular_f",
    "ADJ_DE_SINGULAR_M": "adjective/de_singular_m",
    "ADVERB_DE_BASE": "adverb/de_base",
    "ARTICLE_DE_FEMININE_SINGULAR": "article/de_feminine_singular",
    "ARTICLE_DE_MASCULINE_SINGULAR": "article/de_masculine_singular",
    "ARTICLE_DE_NEUTER_SINGULAR": "article/de_neuter_singular",
    "ARTICLE_DE_PLURAL": "article/de_plural",
    "NUMERAL_DE_CARDINAL_F": "numeral/de_cardinal_f",
    "NUMERAL_DE_CARDINAL_M": "numeral/de_cardinal_m",
    "NUMERAL_DE_CARDINAL_N": "numeral/de_cardinal_n",
    "NUMERAL_DE_ORDINAL": "numeral/de_ordinal",
    "PRONOUN_DE_ACCUSATIVE": "pronoun/de_accusative",
    "PRONOUN_DE_DATIVE": "pronoun/de_dative",
    "PRONOUN_DE_GENITIVE": "pronoun/de_genitive",
    "PRONOUN_DE_NOMINATIVE": "pronoun/de_nominative",
    "PRONOUN_DE_POSSESSIVE": "pronoun/de_possessive",
    "PRONOUN_DE_REFLEXIVE": "pronoun/de_reflexive",
    "VERB_DE_3P_F_FUTURE": "verb/de_3p-f_future",
    "VERB_DE_3P_F_PAST": "verb/de_3p-f_past",
    "VERB_DE_3P_F_PRESENT": "verb/de_3p-f_present",
    "VERB_DE_3P_M_FUTURE": "verb/de_3p-m_future",
    "VERB_DE_3P_M_PAST": "verb/de_3p-m_past",
    "VERB_DE_3P_M_PRESENT": "verb/de_3p-m_present",
    "VERB_DE_3S_F_FUTURE": "verb/de_3s-f_future",
    "VERB_DE_3S_F_PAST": "verb/de_3s-f_past",
    "VERB_DE_3S_F_PRESENT": "verb/de_3s-f_present",
    "VERB_DE_3S_M_FUTURE": "verb/de_3s-m_future",
    "VERB_DE_3S_M_PAST": "verb/de_3s-m_past",
    "VERB_DE_3S_M_PRESENT": "verb/de_3s-m_present",
}
