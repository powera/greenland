#!/usr/bin/env python3
"""
Hangul decomposition helper for Korean text.

Decomposes composed Hangul syllables (U+AC00–U+D7A3) into their constituent
jamo (consonants and vowels).  This is useful for dictionary sort keys, since
the decomposed form sorts by leading consonant (초성), then vowel (중성),
then final consonant (종성) — matching standard Korean dictionary order.

No external libraries required; uses only Unicode arithmetic.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Hangul syllable block range
_HANGUL_BASE = 0xAC00
_HANGUL_END = 0xD7A3

# Jamo tables — index position corresponds to the offset in the syllable formula:
#   syllable = (choseong * 21 + jungseong) * 28 + jongseong + 0xAC00

# 19 leading consonants (초성)
CHOSEONG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")

# 21 vowels (중성)
JUNGSEONG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")

# 28 trailing consonants (종성) — index 0 means no trailing consonant
JONGSEONG = [
    "",
    "ㄱ",
    "ㄲ",
    "ㄳ",
    "ㄴ",
    "ㄵ",
    "ㄶ",
    "ㄷ",
    "ㄹ",
    "ㄺ",
    "ㄻ",
    "ㄼ",
    "ㄽ",
    "ㄾ",
    "ㄿ",
    "ㅀ",
    "ㅁ",
    "ㅂ",
    "ㅄ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]

# All 19 leading consonants in standard South Korean dictionary order.
# Tense (doubled) consonants immediately follow their base consonant.
ALPHABET_CONSONANTS = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")


def is_hangul_syllable(char: str) -> bool:
    """Check if a character is a composed Hangul syllable."""
    cp = ord(char)
    return _HANGUL_BASE <= cp <= _HANGUL_END


def decompose_syllable(char: str) -> str:
    """Decompose a single Hangul syllable into its jamo components.

    Example: '한' → 'ㅎㅏㄴ'

    Non-Hangul characters are returned unchanged.
    """
    cp = ord(char)
    if not (_HANGUL_BASE <= cp <= _HANGUL_END):
        return char

    offset = cp - _HANGUL_BASE
    cho = offset // (21 * 28)
    jung = (offset % (21 * 28)) // 28
    jong = offset % 28

    return CHOSEONG[cho] + JUNGSEONG[jung] + JONGSEONG[jong]


def decompose_hangul(text: str) -> Optional[str]:
    """Decompose all Hangul syllables in text into jamo.

    Example: '바나나' → 'ㅂㅏㄴㅏㄴㅏ'

    Non-Hangul characters (spaces, punctuation, Latin) are kept as-is.

    Returns None if text is empty.
    """
    if not text:
        return None

    try:
        return "".join(decompose_syllable(ch) for ch in text)
    except Exception as e:
        logger.warning(f"Failed to decompose Hangul for '{text}': {e}")
        return None
