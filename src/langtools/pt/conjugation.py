"""Rule-based Portuguese verb conjugation for common regular patterns."""

from typing import Dict, Optional, Tuple

_PRESENT_ENDINGS: Dict[str, Tuple[str, str, str, str, str, str]] = {
    "ar": ("o", "as", "a", "amos", "ais", "am"),
    "er": ("o", "es", "e", "emos", "eis", "em"),
    "ir": ("o", "es", "e", "imos", "is", "em"),
}

_PRETERITE_ENDINGS: Dict[str, Tuple[str, str, str, str, str, str]] = {
    "ar": ("ei", "aste", "ou", "amos", "astes", "aram"),
    "er": ("i", "este", "eu", "emos", "estes", "eram"),
    "ir": ("i", "iste", "iu", "imos", "istes", "iram"),
}

_FUTURE_ENDINGS: Tuple[str, str, str, str, str, str] = ("ei", "ás", "á", "emos", "eis", "ão")
_PERSONS: Tuple[str, str, str, str, str, str] = ("1s", "2s", "3s", "1p", "2p", "3p")


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular Portuguese infinitive across present/past/future."""
    infinitive_value = infinitive.strip().lower()
    verb_class = ""
    for candidate in ("ar", "er", "ir"):
        if infinitive_value.endswith(candidate):
            verb_class = candidate
            break

    if not verb_class:
        return None

    stem = infinitive_value[:-2]
    forms: Dict[str, str] = {}
    for index, person in enumerate(_PERSONS):
        forms[f"{person}_present"] = stem + _PRESENT_ENDINGS[verb_class][index]
        forms[f"{person}_past"] = stem + _PRETERITE_ENDINGS[verb_class][index]
        forms[f"{person}_future"] = infinitive_value + _FUTURE_ENDINGS[index]

    return forms
