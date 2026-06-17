"""Collation data for Brahmic-script languages (Devanagari, Bengali, Tamil, Kannada, Gurmukhi).

Independent letters are in canonical varnamala order within each script's
primary Unicode block, but we still remap to single-character ASCII so every
sort_key is plain ASCII and any SQLite collation engine sorts them correctly
without knowing the script.  Combining marks (matras, vowel signs, virama/halant,
tone marks) are stripped before lookup so they don't perturb word-initial
ordering.

Caveat: alphabet order here is the standard varnamala for word-initial
independent letters.  Conjuncts (joined by virama) still sort sensibly because
the virama is stripped, leaving the base consonants in order.
"""

import unicodedata
from typing import Dict, List

from langtools.family._position_codes import build_position_codes

# Hindi (Devanagari): vowels then consonants in standard varnamala order.
HI_LETTERS_LOWER: List[str] = list("अआइईउऊऋएऐओऔ" "कखगघङ" "चछजझञ" "टठडढण" "तथदधन" "पफबभम" "यरलवशषसह")

# Bengali: vowels then consonants in standard order.
BN_LETTERS_LOWER: List[str] = list("অআইঈউঊঋএঐওঔ" "কখগঘঙ" "চছজঝঞ" "টঠডঢণ" "তথদধন" "পফবভম" "যরলশষসহ")

# Tamil: 12 vowels and 18 consonants in standard order.  No aspirate series.
TA_LETTERS_LOWER: List[str] = list("அஆஇஈஉஊஎஏஐஒஓஔ" "கஙசஞடணதநபமயரலவழளறன")

# Kannada: vowels then consonants in standard varnamala order.
KN_LETTERS_LOWER: List[str] = list(
    "ಅಆಇಈಉಊಋಎಏಐಒಓಔ" "ಕಖಗಘಙ" "ಚಛಜಝಞ" "ಟಠಡಢಣ" "ತಥದಧನ" "ಪಫಬಭಮ" "ಯರಲವಶಷಸಹಳ"
)

# Punjabi (Gurmukhi): the three vowel-bearers (Ura, Aira, Iri) followed by the
# 35 consonants of the painti in standard Gurmukhi alphabet order.  Independent
# vowels are formed from the bearers plus matras, which are stripped as
# combining marks before lookup, so word-initial vowels collate via their bearer.
PA_LETTERS_LOWER: List[str] = list("ੳਅੲ" "ਸਹ" "ਕਖਗਘਙ" "ਚਛਜਝਞ" "ਟਠਡਢਣ" "ਤਥਦਧਨ" "ਪਫਬਭਮ" "ਯਰਲਵੜ")

HI_REMAP: Dict[str, str] = build_position_codes(HI_LETTERS_LOWER)
BN_REMAP: Dict[str, str] = build_position_codes(BN_LETTERS_LOWER)
TA_REMAP: Dict[str, str] = build_position_codes(TA_LETTERS_LOWER)
KN_REMAP: Dict[str, str] = build_position_codes(KN_LETTERS_LOWER)
PA_REMAP: Dict[str, str] = build_position_codes(PA_LETTERS_LOWER)

# Master table for Brahmic position-remapped languages.
REMAP_LANGUAGES: Dict[str, Dict[str, str]] = {
    "hi": HI_REMAP,
    "bn": BN_REMAP,
    "ta": TA_REMAP,
    "kn": KN_REMAP,
    "pa": PA_REMAP,
}


def generate_sort_key(lang_code: str, text: str) -> str:
    """Build a sort key for *text* in the given Brahmic-script language.

    Strips combining marks (matras, vowel signs, virama, tone marks) and remaps
    each remaining independent letter to its single-character ASCII position
    code so binary collation produces canonical alphabet order.
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
