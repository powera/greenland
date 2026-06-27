#!/usr/bin/env python3
"""Deterministic Japanese script analysis for word-level signals.

A Japanese word's writing system is itself a linguistic signal. Words written
with kanji tend to be established native or Sino-Japanese vocabulary -- neither
modern loanwords nor purely grammatical/functional words. This mirrors the
LLM-judged "modern construction" cue stored on
``LemmaTranslation.translation_status`` for Latin and other ancient languages,
but unlike that cue the script of a Japanese string is fully deterministic, so
it is derived on demand here rather than stored on the translation.

The classification deliberately distinguishes "only part kanji" (``MIXED``,
e.g. a stem-plus-okurigana verb like 食べる) from "all kanji" (``KANJI``, e.g.
学校): a word that mixes kanji with kana still carries the kanji signal. Words
with no kanji split into katakana-only (e.g. パン), which typically marks a
modern loanword, and hiragana-only (e.g. が, です), which typically marks
grammatical/functional vocabulary -- exactly the "not modern; not grammatical"
contrast this signal is meant to capture.
"""

import re
from enum import Enum

# Kanji: CJK Unified Ideographs (U+4E00-U+9FFF), Extension A (U+3400-U+4DBF),
# and Compatibility Ideographs (U+F900-U+FAFF), plus the iteration mark
# U+3005 (kurikaeshi) and U+3007, which behave like kanji (e.g. 人々, 時々).
_KANJI_RE = re.compile(r"[々〇㐀-䶿一-鿿豈-﫿]")
# Hiragana block U+3040-U+309F (includes the hiragana iteration marks).
_HIRAGANA_RE = re.compile(r"[぀-ゟ]")
# Katakana block U+30A0-U+30FF plus phonetic extensions (U+31F0-U+31FF) and
# halfwidth katakana (U+FF66-U+FF9D). The prolonged sound mark U+30FC, common
# in loanwords, lives in the main block and so counts as katakana.
_KATAKANA_RE = re.compile(r"[゠-ヿㇰ-ㇿｦ-ﾝ]")


class JapaneseScriptType(Enum):
    """Script composition of a Japanese string, used as a word-level signal.

    The ``KANJI`` and ``MIXED`` members both carry the kanji signal; see
    :pyattr:`has_kanji`. ``NONE`` is returned for strings with no Japanese
    script characters at all (empty, romaji, punctuation only).
    """

    KANJI = "kanji"  # only kanji, e.g. 学校
    MIXED = "mixed"  # kanji plus kana ("only part kanji"), e.g. 食べる
    KATAKANA = "katakana"  # katakana only, no kanji, e.g. パン
    HIRAGANA = "hiragana"  # hiragana only, no kanji, e.g. が
    KANA = "kana"  # both hiragana and katakana, no kanji (uncommon)
    NONE = "none"  # no Japanese script characters

    @property
    def has_kanji(self) -> bool:
        """Whether this script type contains any kanji (``KANJI`` or ``MIXED``)."""
        return self in (JapaneseScriptType.KANJI, JapaneseScriptType.MIXED)


def has_kanji(text: str) -> bool:
    """Return True if the text contains at least one kanji character."""
    return bool(text) and bool(_KANJI_RE.search(text))


def has_hiragana(text: str) -> bool:
    """Return True if the text contains at least one hiragana character."""
    return bool(text) and bool(_HIRAGANA_RE.search(text))


def has_katakana(text: str) -> bool:
    """Return True if the text contains at least one katakana character."""
    return bool(text) and bool(_KATAKANA_RE.search(text))


def contains_japanese(text: str) -> bool:
    """Return True if the text contains any kanji, hiragana, or katakana."""
    return has_kanji(text) or has_hiragana(text) or has_katakana(text)


def kanji_ratio(text: str) -> float:
    """Fraction of Japanese script characters that are kanji (0.0-1.0).

    Only kanji, hiragana, and katakana characters are counted; punctuation,
    spaces, Latin letters, and digits are ignored. Returns 0.0 when the text
    has no Japanese script characters. Useful for telling a mostly-kanji word
    apart from one that is only part kanji.
    """
    if not text:
        return 0.0
    kanji_count = len(_KANJI_RE.findall(text))
    kana_count = len(_HIRAGANA_RE.findall(text)) + len(_KATAKANA_RE.findall(text))
    total = kanji_count + kana_count
    if total == 0:
        return 0.0
    return kanji_count / total


def classify_japanese_script(text: str) -> JapaneseScriptType:
    """Classify the script composition of a Japanese string.

    See :class:`JapaneseScriptType` for the meaning of each category. A string
    mixing kanji with kana (a stem-plus-okurigana word like 食べる) classifies
    as ``MIXED`` rather than ``KANJI``.
    """
    kanji = has_kanji(text)
    hiragana = has_hiragana(text)
    katakana = has_katakana(text)

    if kanji:
        return JapaneseScriptType.MIXED if (hiragana or katakana) else JapaneseScriptType.KANJI
    if hiragana and katakana:
        return JapaneseScriptType.KANA
    if hiragana:
        return JapaneseScriptType.HIRAGANA
    if katakana:
        return JapaneseScriptType.KATAKANA
    return JapaneseScriptType.NONE
