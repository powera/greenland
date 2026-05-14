"""Collation data for the Thai script.

Thai has 44 consonants in canonical alphabet order.  Thai has no case
distinction.  Vowels are stripped (via NFD + Mn removal) before lookup because
Thai dictionary ordering keys primarily on the consonant.

Caveat: preposed vowels (เ แ โ ใ ไ) are written *before* their consonant but
pronounced after.  Strict Thai dictionary ordering requires reordering each
cluster onto its consonant; we don't do that here.  Acceptable for simple
lemma-bucket views — refine if real ordering bugs appear.
"""

import unicodedata
from typing import Dict, List

from langtools.family._position_codes import build_position_codes

TH_LETTERS_LOWER: List[str] = list("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")
TH_REMAP: Dict[str, str] = build_position_codes(TH_LETTERS_LOWER)

REMAP_LANGUAGES: Dict[str, Dict[str, str]] = {
    "th": TH_REMAP,
}


def generate_sort_key(lang_code: str, text: str) -> str:
    """Build a sort key for Thai text.

    Strips combining marks (vowel signs, tone marks) and remaps each remaining
    consonant to its single-character ASCII position code so binary collation
    produces canonical alphabet order.
    """
    char_map = REMAP_LANGUAGES[lang_code]
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    composed = unicodedata.normalize("NFC", stripped)
    parts: List[str] = []
    for ch in composed:
        code = char_map.get(ch)
        if code is not None:
            parts.append(code)
    return "".join(parts)
