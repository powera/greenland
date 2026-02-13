"""Vietnamese grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "vi"
LANGUAGE_NAME = "Vietnamese"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "base_only",
    "query_type": "vietnamese_noun_forms",
    "schema_name": "VietnameseNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "base_only",
    "query_type": "vietnamese_verb_forms",
    "schema_name": "VietnameseVerbForms",
}
