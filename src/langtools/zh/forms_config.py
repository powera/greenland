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

GRAMMATICAL_FORM_OVERRIDES: Dict[str, str] = {
    "ADVERB_ZH_BASE": "adverb/zh_base",
    "NUMERAL_ZH_CARDINAL": "numeral/zh_cardinal",
    "NUMERAL_ZH_ORDINAL": "numeral/zh_ordinal",
    "NUMERAL_ZH_QUANTITY": "numeral/zh_quantity",
    "PRONOUN_ZH_POSSESSIVE": "pronoun/zh_possessive",
    "PRONOUN_ZH_SUBJECTIVE": "pronoun/zh_subjective",
}
