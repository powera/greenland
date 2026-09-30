"""French noun gender predicted from the ending.

This is a cross-check, not a source of facts.  Gender is stored as a
``grammatical_gender`` grammar fact decided by the LLM (see
``words.grammar_fact_tasks.grammatical_gender``); the prediction here only
flags an LLM answer that contradicts a reliable ending, so a reviewer can look
at it.

Only endings that are right for nearly every noun are listed, each with its
common exceptions.  Anything else returns ``None``.
"""

from typing import Dict, Optional, Set, Tuple

# ending -> exceptions (nouns with that ending and the other gender).  Longer
# endings are checked first, so "-ment" is tested before "-t" would be.
_FEMININE_ENDINGS: Dict[str, Set[str]] = {
    "tion": set(),
    "sion": set(),
    "ité": {"comité"},
    "ette": {"squelette"},
    "ance": set(),
    "ence": {"silence"},
    "esse": set(),
    "ure": {"murmure", "mercure", "parjure"},
    "ise": set(),
    "ade": {"stade", "grade"},
    "ie": {"génie", "incendie", "parapluie", "foie", "sosie"},
}

_MASCULINE_ENDINGS: Dict[str, Set[str]] = {
    "ment": {"jument"},
    "isme": set(),
    "age": {"page", "plage", "image", "cage", "nage", "rage"},
    "eau": {"eau", "peau"},
    "oir": set(),
    "ier": set(),
    "ail": set(),
    "eil": set(),
    "et": set(),
}


def _ordered(endings: Dict[str, Set[str]]) -> Tuple[str, ...]:
    return tuple(sorted(endings, key=len, reverse=True))


_FEMININE_ORDER = _ordered(_FEMININE_ENDINGS)
_MASCULINE_ORDER = _ordered(_MASCULINE_ENDINGS)


def _head_noun(noun: str) -> Optional[str]:
    """Return the head of *noun*: the first word, since French is head-first.

    An elided article is dropped ("l'eau" -> "eau").  Capitalised input (a
    proper noun or brand) has no predictable gender and returns ``None``.
    """
    text = noun.strip()
    if "'" in text:
        text = text.split("'", 1)[1]
    if not text or text[0].isupper():
        return None
    head = text.split()[0].split("-")[0]
    return head if head.isalpha() else None


def predict_gender(noun: str) -> Optional[str]:
    """Return ``"masculine"`` or ``"feminine"`` for a reliable ending, else ``None``."""
    head = _head_noun(noun)
    if head is None:
        return None

    for ending in _FEMININE_ORDER:
        if head.endswith(ending):
            return "masculine" if head in _FEMININE_ENDINGS[ending] else "feminine"
    for ending in _MASCULINE_ORDER:
        if head.endswith(ending):
            return "feminine" if head in _MASCULINE_ENDINGS[ending] else "masculine"
    return None
