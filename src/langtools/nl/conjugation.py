"""Rule-based Dutch verb conjugation for common regular patterns."""

from typing import Dict, Optional, Set, Tuple

# Irregular verbs that must NOT be mechanically conjugated.
_IRREGULAR_VERBS: Set[str] = {
    # Fully irregular
    "zijn",
    "hebben",
    "worden",
    "zullen",
    "kunnen",
    "mogen",
    "moeten",
    "willen",
    # Common strong verbs (vowel change in past)
    "gaan",
    "staan",
    "slaan",
    "doen",
    "zien",
    "komen",
    "nemen",
    "geven",
    "lezen",
    "spreken",
    "breken",
    "stelen",
    "schrijven",
    "rijden",
    "blijven",
    "kijken",
    "vinden",
    "binden",
    "drinken",
    "zingen",
    "springen",
    "beginnen",
    "winnen",
    "zwemmen",
    "helpen",
    "sterven",
    "werpen",
    "treffen",
    "eten",
    "vergeten",
    "zitten",
    "liggen",
    "bidden",
    "lopen",
    "vliegen",
    "bieden",
    "sluiten",
    "buigen",
    "ruiken",
    "houden",
    "vallen",
    "hangen",
    "vangen",
    "slapen",
    "laten",
    "roepen",
    "weten",
    "denken",
    "brengen",
    "kopen",
    "zoeken",
    "vragen",
}

_PERSONS: Tuple[str, str, str, str, str, str] = ("1s", "2s", "3s", "1p", "2p", "3p")


def _is_t_kofschip(stem: str) -> bool:
    return stem.endswith(("t", "k", "f", "s", "ch", "p", "x"))


def _normalize_stem(infinitive_value: str) -> Tuple[str, str]:
    """Return (display_stem, raw_stem) where raw_stem preserves v/z for 't kofschip."""
    raw_stem = infinitive_value[:-2]
    stem = raw_stem
    if len(stem) >= 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
        # Doubled consonant marks a closed short syllable: degeminate and do
        # NOT lengthen the vowel (pakken → pak, zetten → zet).
        stem = stem[:-1]
    elif (
        len(stem) >= 3
        and stem[-1] not in "aeiou"
        and stem[-2] in "aeiou"
        and stem[-3] not in "aeiou"
    ):
        # Double open-syllable vowels: CVC → CVVC (e.g. mak → maak)
        stem = stem[:-2] + stem[-2] + stem[-2] + stem[-1]
    # Dutch stem-final devoicing: v→f, z→s
    # The raw_stem (before devoicing) is used for 't kofschip determination,
    # since the underlying consonant is voiced (lev→leef, but past uses -de).
    if stem.endswith("v"):
        stem = stem[:-1] + "f"
    elif stem.endswith("z"):
        stem = stem[:-1] + "s"
    return stem, raw_stem


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a regular Dutch infinitive across present/past/future."""
    infinitive_value = infinitive.strip().lower()
    if not infinitive_value.endswith("en") or len(infinitive_value) < 3:
        return None

    if infinitive_value in _IRREGULAR_VERBS:
        return None

    stem, raw_stem = _normalize_stem(infinitive_value)
    if not stem:
        return None

    # Use the raw (pre-devoicing) stem for 't kofschip: lev → -de (not -te)
    past_suffix = "te" if _is_t_kofschip(raw_stem) else "de"

    # A stem already ending in -t does not take another -t (praten → praat,
    # zetten → zet).
    t_ending = "" if stem.endswith("t") else "t"
    present = (
        stem,
        stem + t_ending,
        stem + t_ending,
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
