"""Korean grammatical structure — single source of truth.

Used by form_patterns.py to auto-generate enum members, form_registry entries,
and task configurations.
"""

from typing import Any, Dict

LANGUAGE_CODE = "ko"
LANGUAGE_NAME = "Korean"

# Korean nouns have no grammatical number or gender inflection.
# Case and topic are marked by postpositional particles.
NOUN_CONFIG: Dict[str, Any] = {
    "type": "base_only",
    "query_type": "korean_noun_forms",
    "schema_name": "KoreanNounForms",
}

# Korean verbs conjugate for tense, aspect, mood, and speech level.
# We store the three haeyo-che (polite informal) tense forms, which are
# the most practical for learners.
VERB_CONFIG: Dict[str, Any] = {
    "type": "explicit",
    "forms": ["polite_present", "polite_past", "polite_future"],
    "query_type": "korean_verb_conjugations",
    "schema_name": "KoreanVerbConjugations",
    "form_descriptions": {
        "polite_present": "haeyo-che present (e.g. 먹어요)",
        "polite_past": "haeyo-che past (e.g. 먹었어요)",
        "polite_future": "haeyo-che future (e.g. 먹을 거예요)",
    },
}
