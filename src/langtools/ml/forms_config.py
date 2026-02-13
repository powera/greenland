"""Malayalam grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "ml"
LANGUAGE_NAME = "Malayalam"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "singular_plural",
    "query_type": "malayalam_noun_forms",
    "schema_name": "MalayalamNounForms",
}

# Malayalam verbs conjugate by tense; person/number agreement is less
# prominent in modern Malayalam, but we use the standard 6-person schema
# for consistency with other Dravidian languages.
VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "malayalam_verb_conjugations",
    "schema_name": "MalayalamVerbConjugations",
}
