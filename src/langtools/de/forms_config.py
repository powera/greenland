"""German grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict, List

LANGUAGE_CODE = "de"
LANGUAGE_NAME = "German"

CASES: List[str] = ["nominative", "accusative", "dative", "genitive"]

NOUN_CONFIG: Dict[str, Any] = {
    "type": "case_number",
    "cases": CASES,
    "numbers": ["singular", "plural"],
    "query_type": "german_noun_forms",
    "schema_name": "GermanNounDeclensions",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "person_tense",
    "persons": ["1s", "2s", "3s", "1p", "2p", "3p"],
    "tenses": ["present", "past", "future"],
    "query_type": "german_verb_conjugations",
    "schema_name": "GermanVerbConjugations",
}
