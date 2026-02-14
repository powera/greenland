"""Burmese grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "my"
LANGUAGE_NAME = "Burmese"

# Burmese is an isolating language; nouns do not inflect for number.
# Plurality is indicated by particles or context.
NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "burmese_noun_forms",
    "schema_name": "BurmeseNounForms",
}

# Burmese verbs do not conjugate for person or number.  Tense and aspect
# are indicated by sentence-final particles.
VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "burmese_verb_forms",
    "schema_name": "BurmeseVerbForms",
}
