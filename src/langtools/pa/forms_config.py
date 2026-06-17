"""Punjabi grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "pa"
LANGUAGE_NAME = "Punjabi"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "punjabi_noun_forms",
    "schema_name": "PunjabiNounForms",
}

# Punjabi verbs conjugate for person, number, gender, tense, and aspect.
# Like Hindi, the periphrastic tense system uses auxiliary verbs, so we store
# the three main tense constructions rather than person-inflected forms.
VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "punjabi_verb_forms",
    "schema_name": "PunjabiVerbForms",
}
