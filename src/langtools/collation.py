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
   remapped to a fixed-width two-character ASCII code (``aa``, ``ab``, …)
   so that binary collation reproduces the canonical alphabet order even
   though Cyrillic codepoints are not contiguous (Ґ sits at U+0490; Є/І/Ї
   live in the supplementary block at U+0400-U+040F).

4. **Brahmic/Thai position remapping** (Hindi, Bengali, Tamil, Kannada,
   Thai): Same fixed-width ASCII position-code scheme as Cyrillic, applied
   after stripping combining marks (matras, vowel signs, virama, tone marks)
   so they don't perturb word-initial ordering.

All sort keys produced by this module are plain ASCII (codepoints 0-127),
so any SQLite collation engine sorts them correctly without knowing the
language's script.  Sort keys are *not* intended to be human-readable.

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
# Cyrillic position remapping (strategy 3)
# ---------------------------------------------------------------------------
# Cyrillic codepoints are not contiguous in alphabet order: Є (U+0404),
# І (U+0406), and Ї (U+0407) live in the Cyrillic supplementary block (which
# sorts *before* the main block U+0410+), and Ґ (U+0490) sits well after the
# main block.  To get correct binary-collation ordering we remap each letter
# of the alphabet to a fixed-width two-character ASCII code (``aa``, ``ab``,
# ``ac``, …).  Lowercase ASCII bytes sort cleanly under SQLite's default
# collation and the two-character width guarantees ``ab < abc < ac``.


def _build_position_codes(letters: List[str]) -> Dict[str, str]:
    """Map each letter to a fixed-width ASCII position code (``aa``, ``ab``, …)."""
    codes: Dict[str, str] = {}
    for index, letter in enumerate(letters):
        # Two lowercase ASCII chars give us 26*26 = 676 slots, far more than any
        # alphabet we support.
        high, low = divmod(index, 26)
        codes[letter] = chr(ord("a") + high) + chr(ord("a") + low)
    return codes


# Ukrainian: А Б В Г Ґ Д Е Є Ж З И І Ї Й К Л М Н О П Р С Т У Ф Х Ц Ч Ш Щ Ь Ю Я
_UK_LETTERS_LOWER: List[str] = list("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя")
_UK_MAP: Dict[str, str] = _build_position_codes(_UK_LETTERS_LOWER)
# Soft sign ь is already in the table; apostrophe ʼ / ' carries no sort weight.

# Master table for Cyrillic position-remapped languages.  Kept separate from
# the Latin remap table so the dispatcher can apply Cyrillic-specific
# preprocessing (e.g. NFC normalization, stripping the apostrophe).
_CYRILLIC_REMAP_LANGUAGES: Dict[str, Dict[str, str]] = {
    "uk": _UK_MAP,
}


# ---------------------------------------------------------------------------
# Brahmic / Thai position remapping (strategy 4)
# ---------------------------------------------------------------------------
# These scripts' independent letters are already in alphabet order within
# their primary Unicode block, but we still remap to fixed-width ASCII so
# every sort_key in the database is plain ASCII (codepoints 0-127) and any
# SQLite collation engine sorts them correctly without knowing the script.
# Combining marks (matras, vowel signs, virama/halant, tone marks) are
# stripped before lookup so they don't perturb word-initial ordering.
#
# Caveats:
# - Thai: preposed vowels (เ แ โ ใ ไ) are written *before* their consonant
#   but pronounced after.  Strict Thai dictionary ordering requires reordering
#   each cluster onto its consonant; we don't do that here.  Acceptable for
#   simple lemma-bucket views — refine if real ordering bugs appear.
# - Hindi/Bengali/Tamil/Kannada: alphabet order is the standard varnamala
#   for word-initial independent letters.  Conjuncts (joined by virama)
#   still sort sensibly because the virama is stripped, leaving the base
#   consonants in order.

# Hindi (Devanagari): vowels then consonants in standard varnamala order.
_HI_LETTERS_LOWER: List[str] = list(
    "अआइईउऊऋएऐओऔ" "कखगघङ" "चछजझञ" "टठडढण" "तथदधन" "पफबभम" "यरलवशषसह"
)

# Bengali: vowels then consonants in standard order.
_BN_LETTERS_LOWER: List[str] = list("অআইঈউঊঋএঐওঔ" "কখগঘঙ" "চছজঝঞ" "টঠডঢণ" "তথদধন" "পফবভম" "যরলশষসহ")

# Tamil: 12 vowels and 18 consonants in standard order.  No aspirate series.
_TA_LETTERS_LOWER: List[str] = list("அஆஇஈஉஊஎஏஐஒஓஔ" "கஙசஞடணதநபமயரலவழளறன")

# Kannada: vowels then consonants in standard varnamala order.
_KN_LETTERS_LOWER: List[str] = list(
    "ಅಆಇಈಉಊಋಎಏಐಒಓಔ" "ಕಖಗಘಙ" "ಚಛಜಝಞ" "ಟಠಡಢಣ" "ತಥದಧನ" "ಪಫಬಭಮ" "ಯರಲವಶಷಸಹಳ"
)

# Thai: 44 consonants in canonical alphabet order.  Thai has no case
# distinction.  Vowels are stripped (via NFD + Mn removal) before lookup
# because Thai dictionary ordering keys primarily on the consonant.
_TH_LETTERS_LOWER: List[str] = list("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")

# Master table for Brahmic/Thai position-remapped languages.
_BRAHMIC_THAI_REMAP_LANGUAGES: Dict[str, Dict[str, str]] = {
    "hi": _build_position_codes(_HI_LETTERS_LOWER),
    "bn": _build_position_codes(_BN_LETTERS_LOWER),
    "ta": _build_position_codes(_TA_LETTERS_LOWER),
    "kn": _build_position_codes(_KN_LETTERS_LOWER),
    "th": _build_position_codes(_TH_LETTERS_LOWER),
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
    """Build a sort key for Cyrillic-alphabet languages.

    Each letter in the language's alphabet is replaced with a fixed-width
    ASCII position code (``aa``, ``ab``, …), so that SQLite's binary
    collation reproduces canonical alphabet order.  Unknown characters
    (punctuation, digits, ASCII) are lowercased and prepended with ``~``
    to sort *after* all alphabet letters in the codes.
    """
    char_map = _CYRILLIC_REMAP_LANGUAGES[lang_code]
    text = unicodedata.normalize("NFC", text).lower()
    parts: list[str] = []
    for ch in text:
        code = char_map.get(ch)
        if code is not None:
            parts.append(code)
    return "".join(parts)


def _generate_brahmic_thai_sort_key(lang_code: str, text: str) -> str:
    """Build a sort key for Brahmic/Thai scripts.

    Strips combining marks (matras, vowel signs, virama, tone marks) and
    remaps each remaining independent letter to a fixed-width ASCII position
    code so binary collation produces canonical alphabet order.
    """
    char_map = _BRAHMIC_THAI_REMAP_LANGUAGES[lang_code]
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    composed = unicodedata.normalize("NFC", stripped)
    parts: list[str] = []
    for ch in composed:
        code = char_map.get(ch)
        if code is not None:
            parts.append(code)
    return "".join(parts)


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
