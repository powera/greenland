"""Rule-based German verb conjugation for common regular patterns."""

from typing import Dict, Optional, Tuple

_PRESENT_ENDINGS: Tuple[str, str, str, str, str, str] = ("e", "st", "t", "en", "t", "en")
_PAST_ENDINGS: Tuple[str, str, str, str, str, str] = ("te", "test", "te", "ten", "tet", "ten")
_FUTURE_AUX: Tuple[str, str, str, str, str, str] = (
    "werde",
    "wirst",
    "wird",
    "werden",
    "werdet",
    "werden",
)
_PERSONS: Tuple[str, str, str, str, str, str] = ("1s", "2s", "3s", "1p", "2p", "3p")


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular German infinitive across present/past/future."""
    infinitive_value = infinitive.strip().lower()
    if not infinitive_value.endswith(("en", "n")):
        return None

    stem = infinitive_value[:-2] if infinitive_value.endswith("en") else infinitive_value[:-1]
    if not stem:
        return None

    forms: Dict[str, str] = {}
    for index, person in enumerate(_PERSONS):
        forms[f"{person}_present"] = stem + _PRESENT_ENDINGS[index]
        forms[f"{person}_past"] = stem + _PAST_ENDINGS[index]
        forms[f"{person}_future"] = _FUTURE_AUX[index] + " " + infinitive_value

    return forms
