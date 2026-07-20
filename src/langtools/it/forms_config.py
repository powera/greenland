"""Italian grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "it"
LANGUAGE_NAME = "Italian"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "italian_noun_forms",
    "schema_name": "ItalianNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    # TODO: add "infinitive" (citation form) to this verb config; see en/forms_config.py
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "italian_verb_conjugations",
    "schema_name": "ItalianVerbConjugations",
}

ADJECTIVE_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["singular_m", "singular_f", "plural_m", "plural_f"],
    "query_type": "italian_adjective_forms",
    "schema_name": "ItalianAdjectiveForms",
}

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADJ_IT_PLURAL_F": "adjective/it_plural_f",
    "ADJ_IT_PLURAL_M": "adjective/it_plural_m",
    "ADJ_IT_SINGULAR_F": "adjective/it_singular_f",
    "ADJ_IT_SINGULAR_M": "adjective/it_singular_m",
    "ADVERB_IT_BASE": "adverb/it_base",
}
