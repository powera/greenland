"""Rule-based German verb conjugation for common regular patterns."""

from typing import Dict, Optional, Set, Tuple

# Irregular / strong / modal verbs that must NOT be mechanically conjugated.
_IRREGULAR_VERBS: Set[str] = {
    # Auxiliary & copula
    "sein",
    "haben",
    "werden",
    # Modal verbs
    "können",
    "müssen",
    "wollen",
    "sollen",
    "dürfen",
    "mögen",
    # Common strong verbs (stem-changing or irregular past)
    "gehen",
    "kommen",
    "geben",
    "nehmen",
    "sprechen",
    "sehen",
    "fahren",
    "laufen",
    "tragen",
    "schlagen",
    "fallen",
    "halten",
    "lassen",
    "schlafen",
    "lesen",
    "essen",
    "trinken",
    "finden",
    "stehen",
    "liegen",
    "sitzen",
    "helfen",
    "sterben",
    "werfen",
    "treffen",
    "schwimmen",
    "beginnen",
    "gewinnen",
    "singen",
    "springen",
    "bringen",
    "denken",
    "kennen",
    "nennen",
    "brennen",
    "rennen",
    "wissen",
    "tun",
    "ziehen",
    "fliegen",
    "bieten",
    "schließen",
    "schreiben",
    "reiten",
    "schneiden",
    "streiten",
    "bleiben",
    "scheinen",
    "steigen",
    "treiben",
    "rufen",
    "stoßen",
    "brechen",
    "empfehlen",
    "erschrecken",
    "vergessen",
    "gelten",
    "laden",
    "raten",
    "wachsen",
    "waschen",
    "backen",
}

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

    if infinitive_value in _IRREGULAR_VERBS:
        return None

    stem = infinitive_value[:-2] if infinitive_value.endswith("en") else infinitive_value[:-1]
    if not stem:
        return None

    # Insert linking -e- for stems ending in -t, -d, -chn, -ffn, -tm, -dm
    needs_e = stem.endswith(("t", "d")) or stem.endswith(("chn", "ffn", "tm", "dm"))

    # Stems ending in a sibilant (s, ß, z, x, tz) absorb the s of the 2s -st
    # ending: du tanzt (not "tanzst"), du reist (not "reisst").
    sibilant_stem = stem.endswith(("s", "ß", "z", "x"))

    forms: Dict[str, str] = {}
    for index, person in enumerate(_PERSONS):
        pres_ending = _PRESENT_ENDINGS[index]
        past_ending = _PAST_ENDINGS[index]
        # Insert linking -e- for stems ending in -t/-d:
        # present: before -st and -t (2s, 3s, 2p)
        # past: before ALL endings (they all start with t-)
        if needs_e and pres_ending in ("st", "t"):
            pres_ending = "e" + pres_ending
        elif sibilant_stem and pres_ending == "st":
            pres_ending = "t"  # 2s: sibilant + -st -> -t
        if needs_e:
            past_ending = "e" + past_ending
        forms[f"{person}_present"] = stem + pres_ending
        forms[f"{person}_past"] = stem + past_ending
        forms[f"{person}_future"] = _FUTURE_AUX[index] + " " + infinitive_value

    return forms
