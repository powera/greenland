"""Sinhala grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "si"
LANGUAGE_NAME = "Sinhala"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "sinhala_noun_forms",
    "schema_name": "SinhalaNounForms",
}

# Sinhala verbs conjugate for tense and formality level.  We use the
# standard 6-person schema for consistency.
VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "sinhala_verb_conjugations",
    "schema_name": "SinhalaVerbConjugations",
}
