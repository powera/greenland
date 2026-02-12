"""Mechanical Lithuanian verb conjugation from three principal parts.

Lithuanian verb forms can be derived from three principal parts:
  1. Infinitive (e.g., "dirbti")
  2. 3rd person present (e.g., "dirba")
  3. 3rd person past (e.g., "dirbo")

The 3rd person present determines the conjugation class:
  - Conjugation I: ends in -a (e.g., dirba, eina, kenčia)
  - Conjugation II: ends in -i (e.g., myli, girdi, turi)
  - Conjugation III: ends in -o (e.g., rašo, skaito, daro)

The 3rd person past determines the past tense type:
  - ė-preterite: ends in -ė (e.g., kentė, rašė, valgė)
  - o-preterite: ends in -o (e.g., dirbo, mylėjo, ėjo)

The only truly irregular verb is būti (to be), whose present tense
cannot be derived mechanically and is hard-coded.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Hard-coded forms for būti (to be) — the only irregular verb.
# Past and future are actually regular, but we hard-code all forms
# for clarity and correctness.
_BUTI_FORMS: Dict[str, str] = {
    "1s_present": "esu",
    "2s_present": "esi",
    "3s_present": "yra",
    "1p_present": "esame",
    "2p_present": "esate",
    "3p_present": "yra",
    "1s_past": "buvau",
    "2s_past": "buvai",
    "3s_past": "buvo",
    "1p_past": "buvome",
    "2p_past": "buvote",
    "3p_past": "buvo",
    "1s_future": "būsiu",
    "2s_future": "būsi",
    "3s_future": "būs",
    "1p_future": "būsime",
    "2p_future": "būsite",
    "3p_future": "būs",
}


def _palatalize_final(stem: str) -> str:
    """Apply Lithuanian palatalization to the final consonant of a stem.

    Before front-vowel endings (-iu, -iau), the consonants t and d
    undergo palatalization:
      - t → č
      - d → dž

    Other consonants (l, r, n, k, g, etc.) are unchanged.
    """
    if stem.endswith("d"):
        return stem[:-1] + "dž"
    if stem.endswith("t"):
        return stem[:-1] + "č"
    return stem


def _make_future_stem(infinitive: str) -> str:
    """Derive the future tense stem from the infinitive.

    Removes -ti, then appends -s with sibilant assimilation:
      - ž + s → š
      - š + s → š  (absorbed)
      - z + s → s
      - s + s → s  (absorbed)
    """
    if infinitive.endswith("ti"):
        inf_stem = infinitive[:-2]
    elif infinitive.endswith("tis"):
        # Reflexive — strip -tis for the stem computation
        inf_stem = infinitive[:-3]
    else:
        logger.warning(f"Infinitive '{infinitive}' does not end in -ti or -tis")
        return infinitive

    # Apply sibilant assimilation
    if inf_stem.endswith("ž"):
        return inf_stem[:-1] + "š"
    if inf_stem.endswith("š"):
        return inf_stem  # š + s → š
    if inf_stem.endswith("z"):
        return inf_stem[:-1] + "s"
    if inf_stem.endswith("s"):
        return inf_stem  # s + s → s
    return inf_stem + "s"


def _conjugate_present(present_3: str) -> Optional[Dict[str, str]]:
    """Derive all present tense forms from the 3rd person present.

    Conjugation I (ends in -a):
      1s: replace -a with -u
      2s: replace -a with -i (collapse double i)
      1p: 3p + me
      2p: 3p + te

    Conjugation II (ends in -i):
      1s: stem (with palatalization) + iu
      2s: same as 3p
      1p: 3p + me
      2p: 3p + te

    Conjugation III (ends in -o):
      1s: replace -o with -au
      2s: replace -o with -ai
      1p: 3p + me
      2p: 3p + te
    """
    if present_3.endswith("a"):
        # Conjugation I (-a type)
        form_1s = present_3[:-1] + "u"
        form_2s = present_3[:-1] + "i"
        # Collapse double 'i' (e.g., kenčia → kenčii → kenči)
        if form_2s.endswith("ii"):
            form_2s = form_2s[:-1]
        form_1p = present_3 + "me"
        form_2p = present_3 + "te"
    elif present_3.endswith("i"):
        # Conjugation II (-i type)
        stem = present_3[:-1]
        palatalized_stem = _palatalize_final(stem)
        form_1s = palatalized_stem + "iu"
        form_2s = present_3  # same as 3p
        form_1p = present_3 + "me"
        form_2p = present_3 + "te"
    elif present_3.endswith("o"):
        # Conjugation III (-o type)
        stem = present_3[:-1]
        form_1s = stem + "au"
        form_2s = stem + "ai"
        form_1p = present_3 + "me"
        form_2p = present_3 + "te"
    else:
        logger.warning(f"Cannot determine conjugation class from 3rd person present '{present_3}'")
        return None

    return {
        "1s_present": form_1s,
        "2s_present": form_2s,
        "3s_present": present_3,
        "1p_present": form_1p,
        "2p_present": form_2p,
        "3p_present": present_3,
    }


def _conjugate_past(past_3: str) -> Optional[Dict[str, str]]:
    """Derive all past tense forms from the 3rd person past.

    ė-preterite (ends in -ė):
      1s: stem (with palatalization of t→č, d→dž) + iau
      2s: stem + ei
      1p: 3p + me
      2p: 3p + te

    o-preterite (ends in -o):
      1s: stem + au
      2s: stem + ai
      1p: 3p + me
      2p: 3p + te
    """
    if past_3.endswith("ė"):
        # ė-preterite
        stem = past_3[:-1]
        palatalized_stem = _palatalize_final(stem)
        form_1s = palatalized_stem + "iau"
        form_2s = stem + "ei"
        form_1p = past_3 + "me"
        form_2p = past_3 + "te"
    elif past_3.endswith("o"):
        # o-preterite
        stem = past_3[:-1]
        form_1s = stem + "au"
        form_2s = stem + "ai"
        form_1p = past_3 + "me"
        form_2p = past_3 + "te"
    else:
        logger.warning(f"Cannot determine past type from 3rd person past '{past_3}'")
        return None

    return {
        "1s_past": form_1s,
        "2s_past": form_2s,
        "3s_past": past_3,
        "1p_past": form_1p,
        "2p_past": form_2p,
        "3p_past": past_3,
    }


def _conjugate_future(infinitive: str) -> Dict[str, str]:
    """Derive all future tense forms from the infinitive.

    Future stem = infinitive stem + s (with sibilant assimilation).
    Endings: -iu (1s), -i (2s), (bare stem, 3), -ime (1p), -ite (2p).
    """
    future_stem = _make_future_stem(infinitive)

    return {
        "1s_future": future_stem + "iu",
        "2s_future": future_stem + "i",
        "3s_future": future_stem,
        "1p_future": future_stem + "ime",
        "2p_future": future_stem + "ite",
        "3p_future": future_stem,
    }


def conjugate_verb(infinitive: str, present_3: str, past_3: str) -> Optional[Dict[str, str]]:
    """Generate all 18 Lithuanian verb forms from three principal parts.

    Given the infinitive, 3rd person present, and 3rd person past,
    mechanically derives all 6 person forms for present, past, and
    future tenses (6 × 3 = 18 forms).

    Note: 3rd person singular and plural are identical in Lithuanian,
    so both 3s and 3p keys are set to the same value.

    Args:
        infinitive: The infinitive form (e.g., "dirbti").
        present_3: The 3rd person present form (e.g., "dirba").
        past_3: The 3rd person past form (e.g., "dirbo").

    Returns:
        Dict mapping form keys to conjugated forms (18 entries),
        or None if the verb cannot be conjugated mechanically
        (e.g., unrecognized endings).
    """
    # Hard-code būti — the only truly irregular Lithuanian verb
    if infinitive == "būti":
        return dict(_BUTI_FORMS)

    # Reflexive verbs are not yet supported for mechanical conjugation.
    # Their reflexive particle (-si/-s) moves position across forms.
    if infinitive.endswith("tis"):
        logger.info(
            f"Reflexive verb '{infinitive}' is not supported for " f"mechanical conjugation"
        )
        return None

    present_forms = _conjugate_present(present_3)
    if present_forms is None:
        return None

    past_forms = _conjugate_past(past_3)
    if past_forms is None:
        return None

    future_forms = _conjugate_future(infinitive)

    all_forms: Dict[str, str] = {}
    all_forms.update(present_forms)
    all_forms.update(past_forms)
    all_forms.update(future_forms)
    return all_forms
