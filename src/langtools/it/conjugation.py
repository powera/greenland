"""Rule-based Italian verb conjugation for common regular patterns."""

from typing import Dict, Optional, Tuple

_PRESENT_ENDINGS: Dict[str, Tuple[str, str, str, str, str, str]] = {
    "are": ("o", "i", "a", "iamo", "ate", "ano"),
    "ere": ("o", "i", "e", "iamo", "ete", "ono"),
    "ire": ("o", "i", "e", "iamo", "ite", "ono"),
}

_IMPERFECT_ENDINGS: Dict[str, Tuple[str, str, str, str, str, str]] = {
    "are": ("avo", "avi", "ava", "avamo", "avate", "avano"),
    "ere": ("evo", "evi", "eva", "evamo", "evate", "evano"),
    "ire": ("ivo", "ivi", "iva", "ivamo", "ivate", "ivano"),
}

_FUTURE_ENDINGS: Tuple[str, str, str, str, str, str] = ("ò", "ai", "à", "emo", "ete", "anno")
_PERSONS: Tuple[str, str, str, str, str, str] = ("1s", "2s", "3s", "1p", "2p", "3p")


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular Italian infinitive across present/past/future."""
    infinitive_value = infinitive.strip().lower()
    verb_class = ""
    for candidate in ("are", "ere", "ire"):
        if infinitive_value.endswith(candidate):
            verb_class = candidate
            break

    if not verb_class:
        return None

    stem = infinitive_value[: -len(verb_class)]
    future_stem = stem + ("er" if verb_class in {"are", "ere"} else "ir")

    forms: Dict[str, str] = {}
    for index, person in enumerate(_PERSONS):
        forms[f"{person}_present"] = stem + _PRESENT_ENDINGS[verb_class][index]
        forms[f"{person}_past"] = stem + _IMPERFECT_ENDINGS[verb_class][index]
        forms[f"{person}_future"] = future_stem + _FUTURE_ENDINGS[index]

    return forms
