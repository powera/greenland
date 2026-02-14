"""Khmer grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "km"
LANGUAGE_NAME = "Khmer"

# Khmer is an isolating language with no inflectional morphology.
# Plurality is expressed through context, numerals, or reduplication.
NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "khmer_noun_forms",
    "schema_name": "KhmerNounForms",
}

# Khmer verbs do not conjugate for person, number, or tense.  Tense
# and aspect are expressed with auxiliary words and context.
VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "khmer_verb_forms",
    "schema_name": "KhmerVerbForms",
}
