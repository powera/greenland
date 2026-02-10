#!/usr/bin/env python3
"""
Latin-alphabet collation sort-key generation.

For languages whose alphabets place accented or special characters in positions
that differ from Unicode code-point order, we generate a *sort key* string
that can be compared with SQLite's default binary collation and produce the
linguistically correct ordering.

Two strategies are used depending on the language:

1. **Position remapping** (Lithuanian, Spanish, Swedish, Vietnamese, and others):
   Characters that are *distinct letters* in the alphabet are remapped to
   ``<base>{`` (first variant after *base*), ``<base>|`` (second variant),
   or ``<base>}`` (third).  Characters ``{`` ``|`` ``}`` all sort after ``z``
   in ASCII/Unicode, so ``a{ < b`` and ``a{ < a|`` hold under binary
   comparison.

2. **Diacritic stripping** (French, German, Irish, Italian, Portuguese):
   Accented characters are *not* separate letters — they sort as their base
   letter.  We strip diacritics via Unicode NFD decomposition so that
   ``é`` → ``e``, ``ü`` → ``u``, ``ç`` → ``c``, etc.

CJK languages (zh, ja, ko) have their own sort-key helpers in their
respective ``langtools`` packages and are **not** handled here.
"""

import unicodedata
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Per-language remapping tables  (strategy 1: position remapping)
# ---------------------------------------------------------------------------
# Keys are *lowercase* characters; values are their sort-key replacements.
# Only characters that need repositioning are listed.

# Lithuanian: A Ą B C Č D E Ę Ė F G H I Į Y J K L M N O P R S Š T U Ų Ū V Z Ž
_LT_MAP: Dict[str, str] = {
    "ą": "a{",
    "č": "c{",
    "ę": "e{",
    "ė": "e|",
    "į": "i{",
    "y": "i|",  # Y sorts between Į and J in Lithuanian
    "j": "j",  # J keeps its position but after the remapped Y
    "š": "s{",
    "ų": "u{",
    "ū": "u|",
    "ž": "z{",
}

# Spanish: … K L M N Ñ O P …
_ES_MAP: Dict[str, str] = {
    "ñ": "n{",
}

# Swedish: standard A-Z then Å Ä Ö (29th, 30th, 31st letters)
_SV_MAP: Dict[str, str] = {
    "å": "z{",
    "ä": "z|",
    "ö": "z}",
}

# Vietnamese: A Ă Â B C D Đ E Ê G H I K L M N O Ô Ơ P Q R S T U Ư V X Y
_VI_MAP: Dict[str, str] = {
    "ă": "a{",
    "â": "a|",
    "đ": "d{",
    "ê": "e{",
    "ô": "o{",
    "ơ": "o|",
    "ư": "u{",
}

# Romanian: A Ă Â B C D E F G H I Î J K L M N O P Q R S Ș T Ț U V W X Y Z
_RO_MAP: Dict[str, str] = {
    "ă": "a{",
    "â": "a|",
    "î": "i{",
    "ș": "s{",
    "ț": "t{",
}

# Polish: A Ą B C Ć D E Ę F G H I J K L Ł M N Ń O Ó P R S Ś T U W Y Z Ź Ż
_PL_MAP: Dict[str, str] = {
    "ą": "a{",
    "ć": "c{",
    "ę": "e{",
    "ł": "l{",
    "ń": "n{",
    "ó": "o{",
    "ś": "s{",
    "ź": "z{",
    "ż": "z|",
}

# Croatian: A B C Č Ć D Đ E F G H I J K L M N O P R S Š T U V Z Ž
# Digraphs Dž, Lj, Nj are separate letters but cannot be handled here.
_HR_MAP: Dict[str, str] = {
    "č": "c{",
    "ć": "c|",
    "đ": "d{",
    "š": "s{",
    "ž": "z{",
}

# Czech: A Á B C Č D Ď E É Ě F G H I Í J K L M N Ň O Ó P Q R Ř S Š T Ť U Ú Ů V W X Y Ý Z Ž
# Digraph Ch sorts after H but cannot be handled with single-char mapping.
_CS_MAP: Dict[str, str] = {
    "á": "a{",
    "č": "c{",
    "ď": "d{",
    "é": "e{",
    "ě": "e|",
    "í": "i{",
    "ň": "n{",
    "ó": "o{",
    "ř": "r{",
    "š": "s{",
    "ť": "t{",
    "ú": "u{",
    "ů": "u|",
    "ý": "y{",
    "ž": "z{",
}

# Danish: standard A–Z then Æ Ø Å (27th, 28th, 29th letters)
_DA_MAP: Dict[str, str] = {
    "æ": "z{",
    "ø": "z|",
    "å": "z}",
}

# Estonian: … S Š Z Ž T U V W Õ Ä Ö Ü
# Š and Ž are distinct letters after S and Z respectively.
# Õ Ä Ö Ü appear at the end of the alphabet.
_ET_MAP: Dict[str, str] = {
    "š": "s{",
    "ž": "z{",
    "õ": "z|",
    "ä": "z}",
    "ö": "z}a",
    "ü": "z}b",
}

# Finnish: standard A–Z then Å Ä Ö (same as Swedish)
_FI_MAP: Dict[str, str] = {
    "å": "z{",
    "ä": "z|",
    "ö": "z}",
}

# Hungarian: accented vowels sort immediately after their base vowel
# Digraphs (cs, dz, dzs, gy, ly, ny, sz, ty, zs) cannot be handled here.
_HU_MAP: Dict[str, str] = {
    "á": "a{",
    "é": "e{",
    "í": "i{",
    "ó": "o{",
    "ö": "o|",
    "ő": "o}",
    "ú": "u{",
    "ü": "u|",
    "ű": "u}",
}

# Latvian: A Ā B C Č D E Ē F G Ģ H I Ī J K Ķ L Ļ M N Ņ O P R S Š T U Ū V Z Ž
_LV_MAP: Dict[str, str] = {
    "ā": "a{",
    "č": "c{",
    "ē": "e{",
    "ģ": "g{",
    "ī": "i{",
    "ķ": "k{",
    "ļ": "l{",
    "ņ": "n{",
    "š": "s{",
    "ū": "u{",
    "ž": "z{",
}

# Maltese: A B Ċ D E F Ġ G GĦ H Ħ I IE J K L M N O P Q R S T U V W X Ż Z
# Digraphs GĦ and IE cannot be handled with single-char mapping.
_MT_MAP: Dict[str, str] = {
    "ċ": "c{",
    "ġ": "g{",
    "ħ": "h{",
    "ż": "z{",
}

# Slovak: A Á Ä B C Č D Ď E É F G H I Í J K L Ĺ Ľ M N Ň O Ó Ô P Q R Ŕ S Š T Ť U Ú V W X Y Ý Z Ž
# Digraphs Ch, Dz, Dž cannot be handled with single-char mapping.
_SK_MAP: Dict[str, str] = {
    "á": "a{",
    "ä": "a|",
    "č": "c{",
    "ď": "d{",
    "é": "e{",
    "í": "i{",
    "ĺ": "l{",
    "ľ": "l|",
    "ň": "n{",
    "ó": "o{",
    "ô": "o|",
    "ŕ": "r{",
    "š": "s{",
    "ť": "t{",
    "ú": "u{",
    "ý": "y{",
    "ž": "z{",
}

# Slovenian: A B C Č D E F G H I J K L M N O P R S Š T U V Z Ž
_SL_MAP: Dict[str, str] = {
    "č": "c{",
    "š": "s{",
    "ž": "z{",
}

# Master table for position-remapped languages.
_REMAP_LANGUAGES: Dict[str, Dict[str, str]] = {
    "lt": _LT_MAP,
    "es": _ES_MAP,
    "sv": _SV_MAP,
    "vi": _VI_MAP,
    "ro": _RO_MAP,
    "pl": _PL_MAP,
    "hr": _HR_MAP,
    "cs": _CS_MAP,
    "da": _DA_MAP,
    "et": _ET_MAP,
    "fi": _FI_MAP,
    "hu": _HU_MAP,
    "lv": _LV_MAP,
    "mt": _MT_MAP,
    "sk": _SK_MAP,
    "sl": _SL_MAP,
}

# ---------------------------------------------------------------------------
# Diacritic-stripping languages  (strategy 2)
# ---------------------------------------------------------------------------
# Accented characters are NOT separate letters; they sort as their base.

_STRIP_LANGUAGES: List[str] = ["de", "fr", "ga", "it", "nl", "pt"]

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# All languages handled by this module.
LATIN_SORT_KEY_LANGUAGES = frozenset(list(_REMAP_LANGUAGES.keys()) + _STRIP_LANGUAGES)


def _strip_diacritics(text: str) -> str:
    """Remove combining diacritical marks via NFD decomposition.

    ``"café"`` → ``"cafe"``, ``"über"`` → ``"uber"``, ``"façade"`` → ``"facade"``.
    """
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


# Vietnamese tone marks (combining characters) to strip.  These are the
# 5 tonal diacritics; we preserve breve (U+0306), circumflex (U+0302),
# and horn (U+031B) which distinguish separate letters (ă, â/ê/ô, ơ/ư).
_VI_TONE_MARKS = frozenset(
    {
        "\u0301",  # COMBINING ACUTE ACCENT       (sắc)
        "\u0300",  # COMBINING GRAVE ACCENT        (huyền)
        "\u0309",  # COMBINING HOOK ABOVE          (hỏi)
        "\u0303",  # COMBINING TILDE               (ngã)
        "\u0323",  # COMBINING DOT BELOW           (nặng)
    }
)


def _strip_vietnamese_tones(text: str) -> str:
    """Remove Vietnamese tone marks while preserving letter-distinguishing marks.

    ``"giống"`` → ``"giống"`` without the tilde → recomposed ``"giông"``?
    No: ``"giống"`` → strip acute from ô → ``"giông"``... actually:

    ``"giống"`` (NFD: g i o + circumflex + tilde n g) → strip tilde →
    ``"giông"`` (NFC: g i ô n g).

    The distinct-letter marks (breve, circumflex, horn) are kept so that
    the remap table can still match ă, â, ê, ô, ơ, ư after recomposition.
    """
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in nfd if ch not in _VI_TONE_MARKS)
    return unicodedata.normalize("NFC", stripped)


def generate_latin_sort_key(lang_code: str, text: str) -> Optional[str]:
    """Return a binary-sortable key for *text* in the given language.

    For position-remapped languages, characters in the remapping table are
    replaced; everything else is lowercased.  For diacritic-stripping
    languages, all diacritics are removed and the result is lowercased.

    Returns ``None`` for unsupported languages or empty input.
    """
    if lang_code not in LATIN_SORT_KEY_LANGUAGES or not text or not text.strip():
        return None

    if lang_code in _REMAP_LANGUAGES:
        char_map = _REMAP_LANGUAGES[lang_code]
        # Vietnamese: strip tone marks first so the remap table can match
        # the base distinct letters (ă, â, đ, ê, ô, ơ, ư).
        if lang_code == "vi":
            text = _strip_vietnamese_tones(text)
        parts: list[str] = []
        for ch in text:
            lower = ch.lower()
            parts.append(char_map.get(lower, lower))
        return "".join(parts)

    # Diacritic-stripping languages (de, fr, it, pt).
    return _strip_diacritics(text).lower()
