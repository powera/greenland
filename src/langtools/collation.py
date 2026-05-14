#!/usr/bin/env python3
"""
Collation sort-key generation for non-CJK languages.

For languages whose alphabets place accented or special characters in positions
that differ from Unicode code-point order, we generate a *sort key* string
that can be compared with SQLite's default binary collation and produce the
linguistically correct ordering.

Strategies used (chosen per language):

1. **Latin position remapping** (Lithuanian, Spanish, Swedish, Vietnamese,
   Turkish, and others): Characters that are *distinct letters* in the
   alphabet are remapped to ``<base>{`` (first variant after *base*),
   ``<base>|`` (second variant), or ``<base>}`` (third).  Characters
   ``{`` ``|`` ``}`` all sort after ``z`` in ASCII/Unicode, so
   ``a{ < b`` and ``a{ < a|`` hold under binary comparison.

2. **Latin diacritic stripping** (French, German, Irish, Italian, Dutch,
   Portuguese): Accented characters are *not* separate letters — they sort
   as their base letter.  We strip diacritics via Unicode NFD decomposition
   so that ``é`` → ``e``, ``ü`` → ``u``, ``ç`` → ``c``, etc.

3. **Cyrillic position remapping** (Ukrainian): Each alphabet letter is
   remapped to a single-character ASCII position code (from the case-invariant
   alphabet defined in ``langtools.family._position_codes``) so binary
   collation reproduces canonical alphabet order even though Cyrillic
   codepoints are not contiguous (Ґ sits at U+0490; Є/І/Ї live in the
   supplementary block at U+0400-U+040F).  Data lives in
   ``langtools/family/cyrillic/collation.py``.

4. **Brahmic/Thai position remapping** (Hindi, Bengali, Tamil, Kannada,
   Thai): Same single-character ASCII position-code scheme as Cyrillic,
   applied after stripping combining marks (matras, vowel signs, virama,
   tone marks) so they don't perturb word-initial ordering.  Data lives in
   ``langtools/family/brahmic/collation.py`` and ``langtools/family/thai/collation.py``.

All sort keys produced by this module are plain ASCII (codepoints 0-127),
so any SQLite collation engine sorts them correctly without knowing the
language's script.  Position-code keys are also case-invariant: uppercasing
or lowercasing a key preserves its ordering relative to other keys.  Sort
keys are *not* intended to be human-readable.

CJK languages (zh, ja, ko) have their own sort-key helpers in their
respective ``langtools`` packages and are **not** handled here.
"""

import unicodedata
from typing import Dict, List, Optional

from langtools.family.brahmic import collation as _brahmic_collation
from langtools.family.cyrillic import collation as _cyrillic_collation
from langtools.family.thai import collation as _thai_collation

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

# Filipino (Tagalog): A B C D E F G H I J K L M N Ñ NG O P Q R S T U V W X Y Z
# NG is a digraph that cannot be handled with single-char mapping.
_TL_MAP: Dict[str, str] = {
    "ñ": "n{",
}

# Malay: standard A-Z Latin alphabet, no special characters needing remapping.
_MS_MAP: Dict[str, str] = {}

# Swahili: standard A-Z Latin alphabet, no special characters needing remapping.
_SW_MAP: Dict[str, str] = {}

# Hausa: A B Ɓ C D Ɗ E F G H I J K Ƙ L M N O P Q R S T U W Y Z ʼY
# Ɓ, Ɗ, Ƙ are distinct implosive/ejective consonants after their base letters.
_HA_MAP: Dict[str, str] = {
    "ɓ": "b{",
    "ɗ": "d{",
    "ƙ": "k{",
}

# Yoruba: A B D E Ẹ F G GB H I J K L M N O Ọ P R S Ṣ T U W Y
# Ẹ, Ọ, Ṣ are distinct letters (with dot below) after their base letters.
# Tone diacritics (acute/grave) are stripped before remapping.
_YO_MAP: Dict[str, str] = {
    "ẹ": "e{",
    "ọ": "o{",
    "ṣ": "s{",
}

# Igbo: A B CH D E F G GH GW H I Ị J K KP KW L M N Ṅ NW NY O Ọ P R S SH T U Ụ W Y Z
# Ị, Ṅ, Ọ, Ụ are distinct letters (with dot below/above) after their base letters.
_IG_MAP: Dict[str, str] = {
    "ị": "i{",
    "ṅ": "n{",
    "ọ": "o{",
    "ụ": "u{",
}

# Zulu: standard A-Z Latin alphabet, no special characters needing remapping.
_ZU_MAP: Dict[str, str] = {}

# Xhosa: standard A-Z Latin alphabet, no special characters needing remapping.
_XH_MAP: Dict[str, str] = {}

# Shona: standard A-Z Latin alphabet, no special characters needing remapping.
_SN_MAP: Dict[str, str] = {}

# Oromo (Qubee): standard A-Z Latin alphabet, long vowels by doubling, no remap needed.
_OM_MAP: Dict[str, str] = {}

# Somali: standard A-Z Latin alphabet, no special characters needing remapping.
_SO_MAP: Dict[str, str] = {}

# Turkish: A B C Ç D E F G Ğ H I İ J K L M N O Ö P R S Ş T U Ü V Y Z
# Ç, Ğ, İ, Ö, Ş, Ü are distinct letters after their base letters.
# Note: Turkish has a unique I/İ distinction (dotless ı/I vs dotted i/İ).
_TR_MAP: Dict[str, str] = {
    "ç": "c{",
    "ğ": "g{",
    "ı": "i",  # dotless ı sorts as regular i position
    "ö": "o{",
    "ş": "s{",
    "ü": "u{",
}

# Azerbaijani: A B C Ç D E Ə F G Ğ H X I İ J K Q L M N O Ö P R S Ş T U Ü V Y Z
# Ç, Ə, Ğ, İ, Ö, Ş, Ü are distinct letters after their base letters.
# Note: Like Turkish, Azerbaijani has the I/İ distinction.
_AZ_MAP: Dict[str, str] = {
    "ç": "c{",
    "ə": "e{",
    "ğ": "g{",
    "ı": "i",  # dotless ı sorts as regular i position
    "ö": "o{",
    "ş": "s{",
    "ü": "u{",
}

# ---------------------------------------------------------------------------
# Cyrillic / Brahmic / Thai position remapping (strategies 3 + 4)
# ---------------------------------------------------------------------------
# Alphabet tables and per-family generators live in ``langtools/family/``.
# The single-character position-code alphabet is defined in
# ``langtools.family._position_codes`` and is case-invariant by construction.

_CYRILLIC_REMAP_LANGUAGES: Dict[str, Dict[str, str]] = _cyrillic_collation.REMAP_LANGUAGES

# Combined Brahmic + Thai remap table preserved under its historical name so
# the existing dispatcher branches below need no rewiring.
_BRAHMIC_THAI_REMAP_LANGUAGES: Dict[str, Dict[str, str]] = {
    **_brahmic_collation.REMAP_LANGUAGES,
    **_thai_collation.REMAP_LANGUAGES,
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
    "tl": _TL_MAP,
    "ms": _MS_MAP,
    "sw": _SW_MAP,
    "ha": _HA_MAP,
    "yo": _YO_MAP,
    "ig": _IG_MAP,
    "zu": _ZU_MAP,
    "xh": _XH_MAP,
    "sn": _SN_MAP,
    "om": _OM_MAP,
    "so": _SO_MAP,
    "tr": _TR_MAP,
    "az": _AZ_MAP,
}

# ---------------------------------------------------------------------------
# Diacritic-stripping languages  (strategy 2)
# ---------------------------------------------------------------------------
# Accented characters are NOT separate letters; they sort as their base.

_STRIP_LANGUAGES: List[str] = ["de", "fr", "ga", "it", "nl", "pt"]

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# Latin-script languages handled by this module.
LATIN_SORT_KEY_LANGUAGES = frozenset(list(_REMAP_LANGUAGES.keys()) + _STRIP_LANGUAGES)

# Non-Latin-script languages handled by this module (Cyrillic + Brahmic + Thai).
NON_LATIN_SORT_KEY_LANGUAGES = frozenset(
    list(_CYRILLIC_REMAP_LANGUAGES.keys()) + list(_BRAHMIC_THAI_REMAP_LANGUAGES.keys())
)

# All languages with collation handled here (excludes CJK which lives in
# language-local helpers under langtools/<lang>/).
SORT_KEY_LANGUAGES = LATIN_SORT_KEY_LANGUAGES | NON_LATIN_SORT_KEY_LANGUAGES


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


# Yoruba and Igbo tone marks (combining characters) to strip.  These are
# tonal diacritics; we preserve dot-below (U+0323) and dot-above (U+0307)
# which distinguish separate letters (ẹ/ọ/ṣ in Yoruba; ị/ọ/ụ/ṅ in Igbo).
_YO_IG_TONE_MARKS = frozenset(
    {
        "\u0301",  # COMBINING ACUTE ACCENT       (high tone)
        "\u0300",  # COMBINING GRAVE ACCENT        (low tone)
        "\u0302",  # COMBINING CIRCUMFLEX          (falling tone, rare)
        "\u030c",  # COMBINING CARON               (rising tone, rare)
    }
)


def _strip_yoruba_igbo_tones(text: str) -> str:
    """Remove Yoruba/Igbo tone marks while preserving letter-distinguishing marks.

    Strips acute and grave accents (tone marks) but keeps dot-below (U+0323)
    and dot-above (U+0307) which distinguish separate letters like ẹ, ọ, ṣ, ṅ.

    ``"àgbàdo"`` → ``"agbado"``, ``"ẹ̀kọ́"`` → ``"ẹkọ"``.
    """
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in nfd if ch not in _YO_IG_TONE_MARKS)
    return unicodedata.normalize("NFC", stripped)


def _turkish_lower(text: str) -> str:
    """Turkish/Azerbaijani-aware lowercasing.

    Handles the dotted/dotless I distinction:
    - İ (U+0130, dotted capital I) -> i (U+0069, dotted lowercase i)
    - I (U+0049, capital I) -> ı (U+0131, dotless lowercase ı)
    All other characters use standard ``str.lower()``.
    """
    result: list[str] = []
    for ch in text:
        if ch == "\u0130":  # İ -> i
            result.append("i")
        elif ch == "I":  # I -> ı
            result.append("\u0131")
        else:
            result.append(ch.lower())
    return "".join(result)


def _generate_cyrillic_sort_key(lang_code: str, text: str) -> str:
    """Delegate to the Cyrillic family generator."""
    return _cyrillic_collation.generate_sort_key(lang_code, text)


def _generate_brahmic_thai_sort_key(lang_code: str, text: str) -> str:
    """Delegate to the Brahmic or Thai family generator based on *lang_code*."""
    if lang_code in _thai_collation.REMAP_LANGUAGES:
        return _thai_collation.generate_sort_key(lang_code, text)
    return _brahmic_collation.generate_sort_key(lang_code, text)


def generate_latin_sort_key(lang_code: str, text: str) -> Optional[str]:
    """Return a binary-sortable key for *text* in the given language.

    Despite the historical name, this function now also handles the
    non-Latin-script languages tracked in ``NON_LATIN_SORT_KEY_LANGUAGES``
    (Cyrillic + Brahmic + Thai).  Prefer ``generate_sort_key`` in new code.

    For Latin position-remapped languages, characters in the remapping table
    are replaced; everything else is lowercased.  For diacritic-stripping
    languages, all diacritics are removed and the result is lowercased.
    For Cyrillic and Brahmic/Thai see ``_generate_cyrillic_sort_key`` and
    ``_generate_brahmic_thai_sort_key``.

    Returns ``None`` for unsupported languages or empty input.
    """
    if lang_code not in SORT_KEY_LANGUAGES or not text or not text.strip():
        return None

    if lang_code in _CYRILLIC_REMAP_LANGUAGES:
        return _generate_cyrillic_sort_key(lang_code, text)

    if lang_code in _BRAHMIC_THAI_REMAP_LANGUAGES:
        return _generate_brahmic_thai_sort_key(lang_code, text)

    if lang_code in _REMAP_LANGUAGES:
        char_map = _REMAP_LANGUAGES[lang_code]
        # Vietnamese: strip tone marks first so the remap table can match
        # the base distinct letters (ă, â, đ, ê, ô, ơ, ư).
        if lang_code == "vi":
            text = _strip_vietnamese_tones(text)
        # Yoruba/Igbo: strip tone marks first so the remap table can match
        # the base distinct letters (ẹ, ọ, ṣ in Yoruba; ị, ọ, ụ, ṅ in Igbo).
        elif lang_code in ("yo", "ig"):
            text = _strip_yoruba_igbo_tones(text)
        # Turkish/Azerbaijani: handle the dotted/dotless I distinction.
        # Python's str.lower() doesn't do Turkish-aware lowering, so we
        # manually map İ -> i and I -> ı before the remap table lookup.
        elif lang_code in ("tr", "az"):
            text = _turkish_lower(text)
        parts: list[str] = []
        for ch in text:
            lower = ch.lower()
            parts.append(char_map.get(lower, lower))
        return "".join(parts)

    # Diacritic-stripping languages (de, fr, ga, it, nl, pt).
    return _strip_diacritics(text).lower()


def generate_sort_key(lang_code: str, text: str) -> Optional[str]:
    """Return a binary-sortable key for *text* in *lang_code*.

    Preferred entrypoint for new code.  Covers all languages in
    ``SORT_KEY_LANGUAGES`` (Latin + Cyrillic + Brahmic + Thai); CJK
    languages are handled by their script-specific helpers in
    ``langtools/<lang>/`` and are not dispatched here.
    """
    return generate_latin_sort_key(lang_code, text)
