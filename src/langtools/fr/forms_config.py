"""French grammatical structure — single source of truth."""

from typing import Any, Dict, List

LANGUAGE_CODE = "fr"
LANGUAGE_NAME = "French"

_PERSONS: List[str] = ["1s", "2s", "3s", "1p", "2p", "3p"]

# pc_* are the past participle in its four agreement forms (parlé, parlée,
# parlés, parlées); which auxiliary builds the passé composé is the
# auxiliary_verb grammar fact.
VERB_FORMS: List[str] = [
    "infinitive",
    *(f"{person}_{tense}" for tense in ["present", "impf", "future"] for person in _PERSONS),
    "pc_m",
    "pc_f",
    "pc_mp",
    "pc_fp",
    "present_participle",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "french_noun_forms",
    "schema_name": "FrenchNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": VERB_FORMS,
    "query_type": "french_verb_conjugations",
    "schema_name": "FrenchVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    # singular_m_prevocalic is the masculine used before a vowel (bel, nouvel,
    # vieil) and is empty for every adjective that has none.
    "forms": ["singular_m", "singular_f", "plural_m", "plural_f", "singular_m_prevocalic"],
    "query_type": "french_adjective_forms",
    "schema_name": "FrenchAdjectiveForms",
}

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADJ_FR_PLURAL_F": "adjective/fr_plural_f",
    "ADJ_FR_PLURAL_M": "adjective/fr_plural_m",
    "ADJ_FR_SINGULAR_F": "adjective/fr_singular_f",
    "ADJ_FR_SINGULAR_M": "adjective/fr_singular_m",
    "ADVERB_FR_BASE": "adverb/fr_base",
    "ARTICLE_FR_FEMININE_SINGULAR": "article/fr_feminine_singular",
    "ARTICLE_FR_MASCULINE_SINGULAR": "article/fr_masculine_singular",
    "ARTICLE_FR_PLURAL": "article/fr_plural",
    "NUMERAL_FR_CARDINAL_F": "numeral/fr_cardinal_f",
    "NUMERAL_FR_CARDINAL_M": "numeral/fr_cardinal_m",
    "NUMERAL_FR_ORDINAL_F": "numeral/fr_ordinal_f",
    "NUMERAL_FR_ORDINAL_M": "numeral/fr_ordinal_m",
    "PRONOUN_FR_OBJECTIVE": "pronoun/fr_objective",
    "PRONOUN_FR_POSSESSIVE": "pronoun/fr_possessive",
    "PRONOUN_FR_REFLEXIVE": "pronoun/fr_reflexive",
    "PRONOUN_FR_SUBJECTIVE": "pronoun/fr_subjective",
    "VERB_FR_1P_PC": "verb/fr_1p_pc",
    "VERB_FR_1S_PC": "verb/fr_1s_pc",
    "VERB_FR_2P_PC": "verb/fr_2p_pc",
    "VERB_FR_2S_PC": "verb/fr_2s_pc",
    "VERB_FR_3P_PC": "verb/fr_3p_pc",
    "VERB_FR_3S_PC": "verb/fr_3s_pc",
}

# Form-generation settings per part of speech; see langtools.form_tasks.
FORM_TASK_SETTINGS: Dict[str, Dict[str, Any]] = {
    "noun": {
        "fetcher": "translation",
        "threshold": 2,
        "generator": "query_french_noun_forms",
        "on_demand": True,
    },
    "verb": {
        "fetcher": "translation",
        "threshold": 20,
        "base_form": "infinitive",
        "generator": "query_french_verb_conjugations",
        "on_demand": True,
    },
    "adjective": {
        "fetcher": "translation",
        "threshold": 4,
        "generator": "query_french_adjective_forms",
        "on_demand": True,
    },
}
