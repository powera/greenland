"""Dutch grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "nl"
LANGUAGE_NAME = "Dutch"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "dutch_noun_forms",
    "schema_name": "DutchNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "dutch_verb_conjugations",
    "schema_name": "DutchVerbConjugations",
}

# Dutch adjectives inflect mainly base vs. -e form; the gender/number set here
# mirrors the cross-language agreement axis and is generated via the LLM. The
# enum members already exist below.
ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["singular_m", "singular_f", "plural_m", "plural_f"],
    "query_type": "dutch_adjective_forms",
    "schema_name": "DutchAdjectiveForms",
}

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADJ_NL_PLURAL_F": "adjective/nl_plural_f",
    "ADJ_NL_PLURAL_M": "adjective/nl_plural_m",
    "ADJ_NL_SINGULAR_F": "adjective/nl_singular_f",
    "ADJ_NL_SINGULAR_M": "adjective/nl_singular_m",
    "ADVERB_NL_BASE": "adverb/nl_base",
}
