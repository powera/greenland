"""Collation data for Cyrillic-script languages.

Cyrillic codepoints are not contiguous in alphabet order: Є (U+0404), І (U+0406),
and Ї (U+0407) live in the Cyrillic supplementary block (which sorts *before*
the main block U+0410+), and Ґ (U+0490) sits well after the main block.  To
get correct binary-collation ordering we remap each letter of the alphabet to
a single-character ASCII position code via ``family._position_codes``.

Future Cyrillic languages (ru, bg, sr, mk, be) should add their alphabet and a
``<XX>_REMAP`` constant here.
"""

import unicodedata
from typing import Dict, List

from langtools.family._position_codes import build_position_codes

# Ukrainian: А Б В Г Ґ Д Е Є Ж З И І Ї Й К Л М Н О П Р С Т У Ф Х Ц Ч Ш Щ Ь Ю Я
UK_LETTERS_LOWER: List[str] = list("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя")
UK_REMAP: Dict[str, str] = build_position_codes(UK_LETTERS_LOWER)

# Master table for Cyrillic position-remapped languages.
REMAP_LANGUAGES: Dict[str, Dict[str, str]] = {
    "uk": UK_REMAP,
}


def generate_sort_key(lang_code: str, text: str) -> str:
    """Build a sort key for *text* in the given Cyrillic-script language.

    Each letter in the language's alphabet is replaced with its single-character
    ASCII position code so binary collation reproduces canonical alphabet order.
    Unknown characters (punctuation, digits, ASCII, soft sign in some inputs,
    apostrophes) carry no sort weight and are dropped.
    """
    char_map = REMAP_LANGUAGES[lang_code]
    text = unicodedata.normalize("NFC", text).lower()
    parts: List[str] = []
    for ch in text:
        code = char_map.get(ch)
        if code is not None:
            parts.append(code)
    return "".join(parts)
