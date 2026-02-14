"""Swedish grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "sv"
LANGUAGE_NAME = "Swedish"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "swedish_noun_forms",
    "schema_name": "SwedishNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "swedish_verb_conjugations",
    "schema_name": "SwedishVerbConjugations",
}

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADVERB_SV_BASE": "adverb/sv_base",
}
