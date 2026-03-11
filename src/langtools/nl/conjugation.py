"""Rule-based Dutch verb conjugation for common regular patterns."""

from typing import Dict, Optional, Tuple

_PERSONS: Tuple[str, str, str, str, str, str] = ("1s", "2s", "3s", "1p", "2p", "3p")


def _is_t_kofschip(stem: str) -> bool:
    return stem.endswith(("t", "k", "f", "s", "ch", "p", "x"))


def _normalize_stem(infinitive_value: str) -> str:
    stem = infinitive_value[:-2]
    if (
        len(stem) >= 3
        and stem[-1] not in "aeiou"
        and stem[-2] in "aeiou"
        and stem[-3] not in "aeiou"
    ):
        return stem[:-2] + stem[-2] + stem[-2] + stem[-1]
    return stem


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular Dutch infinitive across present/past/future."""
    infinitive_value = infinitive.strip().lower()
    if not infinitive_value.endswith("en") or len(infinitive_value) < 3:
        return None

    stem = _normalize_stem(infinitive_value)
    if not stem:
        return None

    past_suffix = "te" if _is_t_kofschip(stem) else "de"

    present = (
        stem,
        stem + "t",
        stem + "t",
        infinitive_value,
        infinitive_value,
        infinitive_value,
    )
    past = (
        stem + past_suffix,
        stem + past_suffix,
        stem + past_suffix,
        stem + past_suffix + "n",
        stem + past_suffix + "n",
        stem + past_suffix + "n",
    )
    future = (
        "zal " + infinitive_value,
        "zult " + infinitive_value,
        "zal " + infinitive_value,
        "zullen " + infinitive_value,
        "zullen " + infinitive_value,
        "zullen " + infinitive_value,
    )

    forms: Dict[str, str] = {}
    for index, person in enumerate(_PERSONS):
        forms[f"{person}_present"] = present[index]
        forms[f"{person}_past"] = past[index]
        forms[f"{person}_future"] = future[index]

    return forms
