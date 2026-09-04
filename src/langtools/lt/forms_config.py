"""Lithuanian grammatical structure — single source of truth."""

from typing import Any, Dict, List

LANGUAGE_CODE = "lt"
LANGUAGE_NAME = "Lithuanian"

CASES: List[str] = [
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "locative",
    "vocative",
]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "lithuanian_noun_declensions",
    "schema_name": "LithuanianNounDeclensions",
    "extra_schema": {
        "number_type": (
            "string",
            "The number type of this noun",
            ["regular", "plurale_tantum", "singulare_tantum"],
        ),
    },
}

VERB_CONFIG: Dict[str, Any] = {
    # TODO: add "infinitive" (citation form) to this verb config; see en/forms_config.py
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future", "conditional"],
    "extra_forms": ["2s_imperative", "2p_imperative", "habitual_past"],
    "query_type": "lithuanian_verb_conjugations",
    "schema_name": "LithuanianVerbConjugations",
}

# Degree forms carried alongside the case table.  A Lithuanian comparative
# declines like any adjective ("raudonesnio obuolio"), so the complete paradigm
# would be 3 degrees x 28 cases = 84 forms.  That is far more than Trakaido
# needs -- the app deliberately avoids drilling declension tables, and picks
# these up through sentences instead -- so only the slots that actually carry
# sentences are stored:
#
#     nominative  "the big apple was redder", "those apples were the reddest"
#     accusative  "he has a redder apple"
#
# in both genders and numbers, giving 8 per degree.  A declined comparative in
# another case (genitive "of the redder apple") has no row and will surface as a
# decomposition miss in sentences.analysis, which matches by surface text -- so
# the gap is observable, and a case can be added when one actually shows up.
_DEGREE_CASES: List[str] = ["nominative", "accusative"]
ADJECTIVE_DEGREE_FORMS: List[str] = [
    f"{degree}_{case}_{number}_{gender}"
    for degree in ("comparative", "superlative")
    for case in _DEGREE_CASES
    for number in ("singular", "plural")
    for gender in ("m", "f")
]

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "case_number_gender",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "genders": ["m", "f"],
    "extra_forms": ADJECTIVE_DEGREE_FORMS,
    "query_type": "lithuanian_adjective_declensions",
    "schema_name": "LithuanianAdjectiveDeclensions",
}

ADVERB_CONFIG: Dict[str, Any] = {
    "type": "degree",
    "forms": ["positive", "comparative", "superlative"],
    "query_type": "lithuanian_adverb_forms",
    "schema_name": "LithuanianAdverbForms",
}

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADVERB_LT_BASE": "adverb/lt_base",
    "NUMERAL_LT_CARDINAL_F": "numeral/lt_cardinal_f",
    "NUMERAL_LT_CARDINAL_M": "numeral/lt_cardinal_m",
    "NUMERAL_LT_ORDINAL_F": "numeral/lt_ordinal_f",
    "NUMERAL_LT_ORDINAL_M": "numeral/lt_ordinal_m",
    "PRONOUN_LT_ACCUSATIVE": "pronoun/lt_accusative",
    "PRONOUN_LT_DATIVE": "pronoun/lt_dative",
    "PRONOUN_LT_GENITIVE": "pronoun/lt_genitive",
    "PRONOUN_LT_INSTRUMENTAL": "pronoun/lt_instrumental",
    "PRONOUN_LT_LOCATIVE": "pronoun/lt_locative",
    "PRONOUN_LT_NOMINATIVE": "pronoun/lt_nominative",
    "PRONOUN_LT_POSSESSIVE": "pronoun/lt_possessive",
    "VERB_LT_3P_F_FUTURE": "verb/lt_3p-f_future",
    "VERB_LT_3P_F_PAST": "verb/lt_3p-f_past",
    "VERB_LT_3P_F_PRESENT": "verb/lt_3p-f_present",
    "VERB_LT_3P_M_FUTURE": "verb/lt_3p-m_future",
    "VERB_LT_3P_M_PAST": "verb/lt_3p-m_past",
    "VERB_LT_3P_M_PRESENT": "verb/lt_3p-m_present",
    "VERB_LT_3S_F_FUTURE": "verb/lt_3s-f_future",
    "VERB_LT_3S_F_PAST": "verb/lt_3s-f_past",
    "VERB_LT_3S_F_PRESENT": "verb/lt_3s-f_present",
    "VERB_LT_3S_M_FUTURE": "verb/lt_3s-m_future",
    "VERB_LT_3S_M_PAST": "verb/lt_3s-m_past",
    "VERB_LT_3S_M_PRESENT": "verb/lt_3s-m_present",
}
