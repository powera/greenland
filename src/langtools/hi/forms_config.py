"""Hindi grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "hi"
LANGUAGE_NAME = "Hindi"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "hindi_noun_forms",
    "schema_name": "HindiNounForms",
}

# Hindi verbs conjugate for person, number, gender, tense, and aspect.
# The periphrastic tense system uses auxiliary verbs, so we store the
# three main tense constructions rather than person-inflected forms.
VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "hindi_verb_forms",
    "schema_name": "HindiVerbForms",
}
