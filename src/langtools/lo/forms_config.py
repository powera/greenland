"""Lao grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "lo"
LANGUAGE_NAME = "Lao"

# Lao is an isolating language closely related to Thai.  Nouns do not
# inflect for number; plurality is expressed through classifiers or context.
NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "lao_noun_forms",
    "schema_name": "LaoNounForms",
}

# Lao verbs do not conjugate for person, number, or tense.  Tense and
# aspect are expressed with auxiliary particles.
VERB_CONFIG: Dict[str, Any] = {
    "type": "tense_only",
    "tenses": ["present", "past", "future"],
    "query_type": "lao_verb_forms",
    "schema_name": "LaoVerbForms",
}
