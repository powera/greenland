"""Rule-based Italian derivative form generation for verbs."""

from typing import Dict, Optional, Set, Tuple

_PERSONS: Tuple[str, str, str, str, str, str] = ("1s", "2s", "3s", "1p", "2p", "3p")

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

_COMMON_IRREGULAR_FORMS: Dict[str, Dict[str, str]] = {
    "essere": {
        "1s_present": "sono",
        "2s_present": "sei",
        "3s_present": "è",
        "1p_present": "siamo",
        "2p_present": "siete",
        "3p_present": "sono",
        "1s_past": "ero",
        "2s_past": "eri",
        "3s_past": "era",
        "1p_past": "eravamo",
        "2p_past": "eravate",
        "3p_past": "erano",
        "1s_future": "sarò",
        "2s_future": "sarai",
        "3s_future": "sarà",
        "1p_future": "saremo",
        "2p_future": "sarete",
        "3p_future": "saranno",
    },
    "avere": {
        "1s_present": "ho",
        "2s_present": "hai",
        "3s_present": "ha",
        "1p_present": "abbiamo",
        "2p_present": "avete",
        "3p_present": "hanno",
        "1s_past": "avevo",
        "2s_past": "avevi",
        "3s_past": "aveva",
        "1p_past": "avevamo",
        "2p_past": "avevate",
        "3p_past": "avevano",
        "1s_future": "avrò",
        "2s_future": "avrai",
        "3s_future": "avrà",
        "1p_future": "avremo",
        "2p_future": "avrete",
        "3p_future": "avranno",
    },
}

_BLOCKED_NON_REGULAR_VERBS: Set[str] = {
    "andare",
    "fare",
    "stare",
    "dare",
    "dire",
    "potere",
    "volere",
    "dovere",
    "sapere",
    "venire",
    "tenere",
    "uscire",
    "salire",
    "morire",
    "rimanere",
    "porre",
    "trarre",
    "tradurre",
    "condurre",
    "bere",
    "sedere",
    "piacere",
    "tacere",
    "capire",
    "finire",
    "preferire",
    "costruire",
    "pulire",
    "spedire",
    "colpire",
    "guarire",
    "obbedire",
    "ubbidire",
    "suggerire",
    "inserire",
    "riferire",
    "sostituire",
    "contribuire",
    "distribuire",
    "attribuire",
    "diminuire",
    "eseguire",
    "istruire",
    "restituire",
    "unire",
    "agire",
    "reagire",
    "gestire",
}


def _infer_verb_class(infinitive: str) -> str:
    for candidate in ("are", "ere", "ire"):
        if infinitive.endswith(candidate):
            return candidate
    return ""


def _adjust_are_stem(stem: str, ending: str, *, is_car_gar: bool, is_ci_gi: bool) -> str:
    """Apply -care/-gare/-ciare/-giare orthography before a front-vowel ending.

    -care/-gare insert an ``h`` to keep the hard c/g sound (cerco -> cerchi),
    while -ciare/-giare drop the stem-final ``i`` that only softened the c/g
    (mangio -> mangi, not "mangii").  Adjustments only apply before endings
    starting with ``e`` or ``i``.
    """
    if ending[:1] not in ("e", "i"):
        return stem
    if is_car_gar:
        return stem + "h"
    if is_ci_gi and stem.endswith("i"):
        return stem[:-1]
    return stem


def _derive_past_stem(verb_class: str, past_1s: str, infinitive: str) -> str:
    expected_ending = _IMPERFECT_ENDINGS[verb_class][0]
    if past_1s.endswith(expected_ending):
        return past_1s[: -len(expected_ending)]
    return infinitive[: -len(verb_class)]


def _derive_future_stem(verb_class: str, future_1s: str, infinitive: str) -> str:
    if future_1s.endswith(_FUTURE_ENDINGS[0]):
        return future_1s[: -len(_FUTURE_ENDINGS[0])]
    stem = infinitive[: -len(verb_class)]
    return stem + ("er" if verb_class in {"are", "ere"} else "ir")


def conjugate(
    infinitive: str,
    present_1s: Optional[str] = None,
    past_1s: Optional[str] = None,
    future_1s: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Conjugate an Italian infinitive using irregular tables + grammar facts.

    If *present_1s* / *past_1s* / *future_1s* are provided (typically from
    grammar facts), those principal parts are used as stems for derived forms.
    """
    infinitive_value = infinitive.strip().lower()
    if infinitive_value in _COMMON_IRREGULAR_FORMS:
        return dict(_COMMON_IRREGULAR_FORMS[infinitive_value])

    verb_class = _infer_verb_class(infinitive_value)
    if not verb_class:
        return None

    if infinitive_value in _BLOCKED_NON_REGULAR_VERBS:
        return None

    default_stem = infinitive_value[: -len(verb_class)]

    # Orthographic adjustments only apply to -are verbs whose stem ends in a
    # hard c/g (-care/-gare) or a softening i (-ciare/-giare).
    is_car_gar = verb_class == "are" and infinitive_value.endswith(("care", "gare"))
    is_ci_gi = verb_class == "are" and infinitive_value.endswith(("ciare", "giare"))

    present_stem = (
        present_1s.strip().lower()[: -len(_PRESENT_ENDINGS[verb_class][0])]
        if present_1s and present_1s.strip().lower().endswith(_PRESENT_ENDINGS[verb_class][0])
        else default_stem
    )
    past_stem = (
        _derive_past_stem(verb_class, past_1s.strip().lower(), infinitive_value)
        if past_1s
        else default_stem
    )
    if future_1s:
        future_stem = _derive_future_stem(verb_class, future_1s.strip().lower(), infinitive_value)
    elif is_car_gar:
        future_stem = default_stem + "her"  # cerc -> cercher(ò)
    elif is_ci_gi:
        future_stem = default_stem[:-1] + "er"  # mangi -> manger(ò)
    else:
        future_stem = default_stem + ("er" if verb_class in {"are", "ere"} else "ir")

    forms: Dict[str, str] = {}
    for index, person in enumerate(_PERSONS):
        present_ending = _PRESENT_ENDINGS[verb_class][index]
        forms[f"{person}_present"] = (
            _adjust_are_stem(present_stem, present_ending, is_car_gar=is_car_gar, is_ci_gi=is_ci_gi)
            + present_ending
        )
        forms[f"{person}_past"] = past_stem + _IMPERFECT_ENDINGS[verb_class][index]
        forms[f"{person}_future"] = future_stem + _FUTURE_ENDINGS[index]

    if present_1s:
        forms["1s_present"] = present_1s.strip().lower()
    if past_1s:
        forms["1s_past"] = past_1s.strip().lower()
    if future_1s:
        forms["1s_future"] = future_1s.strip().lower()

    return forms
