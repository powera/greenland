"""Chinese grammatical structure — single source of truth."""

from typing import Any, Dict

LANGUAGE_CODE = "zh"
LANGUAGE_NAME = "Chinese"

NOUN_CONFIG: Dict[str, Any] = {
    "type": "base_only",
    "query_type": "chinese_noun_forms",
    "schema_name": "ChineseNounForms",
}

VERB_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["base", "perfective", "experiential", "progressive"],
    "query_type": "chinese_verb_forms",
    "schema_name": "ChineseVerbForms",
    "form_descriptions": {
        "base": "bare verb (e.g. 买)",
        "perfective": "verb + 了 — completed action (e.g. 买了)",
        "experiential": "verb + 过 — have done before (e.g. 买过)",
        "progressive": "在 + verb — in progress (e.g. 在买)",
    },
}
