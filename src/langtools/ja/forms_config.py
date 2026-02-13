"""Japanese grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "ja"
LANGUAGE_NAME = "Japanese"

# Japanese nouns have no grammatical number, gender, or case inflection.
NOUN_CONFIG: Dict[str, Any] = {
    "type": "base_only",
    "query_type": "japanese_noun_forms",
    "schema_name": "JapaneseNounForms",
}

# Japanese verbs conjugate into many forms.  We store the four most
# useful for learners.
VERB_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["masu", "te", "ta", "nai"],
    "query_type": "japanese_verb_conjugations",
    "schema_name": "JapaneseVerbConjugations",
    "form_descriptions": {
        "masu": "polite non-past / masu-form (e.g. 食べます)",
        "te": "conjunctive / te-form (e.g. 食べて)",
        "ta": "plain past / ta-form (e.g. 食べた)",
        "nai": "plain negative / nai-form (e.g. 食べない)",
    },
}
