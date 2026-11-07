#!/usr/bin/env python3
"""
Pinyin helper module for Chinese text romanization.

This module provides utilities for generating pinyin transliterations
for Chinese text. Degrades gracefully if required libraries are not available.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from langtools.ruby_html import wrap_unannotated_ruby

logger = logging.getLogger(__name__)

# Try to import pypinyin, gracefully handle if not available
try:
    from pypinyin import Style, lazy_pinyin, pinyin as _pinyin_table
    from pypinyin.constants import PHRASES_DICT as _PHRASES_DICT

    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False
    logger.warning("pypinyin not available - Chinese pinyin transliteration will be disabled")

# Try to import opencc for character conversion (improves pinyin accuracy)
try:
    from langtools.zh.converter import to_simplified, OPENCC_AVAILABLE
except ImportError:
    OPENCC_AVAILABLE = False

    def to_simplified(text: str) -> str:
        return text


# Try to import jieba for word segmentation, gracefully handle if not available
try:
    import jieba

    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logger.warning(
        "jieba not available - Chinese word segmentation will fall back to character-by-character"
    )


def is_chinese(text: str) -> bool:
    """
    Check if the text contains Chinese characters.

    Args:
        text: Text to check

    Returns:
        True if text contains Chinese characters, False otherwise
    """
    if not text:
        return False
    # Check for CJK Unified Ideographs range
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def generate_pinyin(chinese_text: str) -> Optional[str]:
    """
    Generate pinyin for Chinese text with tone marks.

    For better accuracy with polyphonic characters (多音字), the text is first
    converted to simplified Chinese before generating pinyin. This is because
    pypinyin's word segmentation and heteronym handling is better tuned for
    simplified characters.

    Args:
        chinese_text: Chinese text to convert to pinyin (simplified or traditional)

    Returns:
        Pinyin string with tone marks (e.g., "nǐ hǎo"), or None if:
        - pypinyin is not available
        - text is empty
        - text doesn't contain Chinese characters
    """
    if not PYPINYIN_AVAILABLE or not chinese_text:
        return None

    # Only generate pinyin if text actually contains Chinese characters
    if not is_chinese(chinese_text):
        return None

    try:
        # Convert to simplified Chinese first for better pinyin accuracy
        # pypinyin handles simplified characters more reliably for polyphonic chars
        text_for_pinyin = to_simplified(chinese_text)

        # Use Style.TONE to get pinyin with tone marks (e.g., "nǐ hǎo")
        pinyin_list = lazy_pinyin(text_for_pinyin, style=Style.TONE)
        return " ".join(pinyin_list)
    except Exception as e:
        logger.warning(f"Failed to generate pinyin for '{chinese_text}': {e}")
        return None


_HAN_CHAR = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# Syllables that need an apostrophe when they do not start the word: Xī'ān,
# nǚ'ér.  Tone marks are stripped before the test.
_APOSTROPHE_INITIALS = ("a", "o", "e")
_TONE_MARK_FOLD = str.maketrans("āáǎàōóǒòēéěèīíǐìūúǔùǖǘǚǜü", "aaaaooooeeeeiiiiuuuuvvvvv")


# Characters whose everyday readings differ by sense or word (长 cháng "long"
# / zhǎng "grow", 行 xíng / háng).  pypinyin lists rare readings for thousands
# of characters, so asking it alone flags half the vocabulary; only these are
# worth a reviewer's time when no phrase settles them.
COMMON_POLYPHONES: frozenset[str] = frozenset(
    "长行重还乐好发种只着得地都便少数调为应差教觉角传曾分量干空参尽"
    "处当解难背朝薄假间将散相正省更降露几划缝弹扎累哄冲兴称奔担蒙恶强"
    "似宿率塞片圈血盛藏属折转"
)


@dataclass(frozen=True)
class WordReading:
    """The pinyin of one dictionary word, for exports and annotation.

    ``syllables`` has one entry per Han character, in order, so a consumer can
    put a reading over each character; a run of non-Han text (the "T" of T恤)
    is its own entry, unchanged.  ``pinyin`` is the word written as one unit,
    the way dictionaries print it ("yínháng", "Xī'ān" -> "xī'ān").
    ``ambiguous_positions`` lists the indices of ``syllables`` whose character
    has several readings that neither an override nor a pypinyin phrase
    settled: those are guesses and worth a reviewer's look (bare 长 reads
    zhǎng, which is wrong for "long").  ``source`` is ``"override"`` when the
    lemma's ``pinyin`` grammar fact supplied the reading, else ``"pypinyin"``.
    """

    syllables: Tuple[str, ...]
    pinyin: str
    ambiguous_positions: Tuple[int, ...]
    source: str

    @property
    def spaced(self) -> str:
        """Syllables separated by spaces: the WireWord ``target_pinyin`` style."""
        return " ".join(self.syllables)

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguous_positions)


def _split_runs(text: str) -> List[str]:
    """Split *text* into single Han characters and maximal non-Han runs."""
    pieces: List[str] = []
    buffer = ""
    for char in text:
        if _HAN_CHAR.match(char):
            if buffer.strip():
                pieces.append(buffer.strip())
            buffer = ""
            pieces.append(char)
        else:
            buffer += char
    if buffer.strip():
        pieces.append(buffer.strip())
    return pieces


# Adjectives are stored with attributive 的 (正确的).  Word-final, it is the
# particle "de" and is written apart from the word: zhèngquè de.
_ATTRIBUTIVE_SUFFIX = "的"


def _join_word(syllables: Tuple[str, ...], breaks: frozenset[int]) -> str:
    """Write syllables as one unit, with a space before each index in *breaks*.

    Within a word, syllables run together with the apostrophe pinyin requires
    (xī'ān); *breaks* marks where a new word starts (使更活泼 -> shǐ gèng huópō),
    a non-Han run begins or ends, or a word-final particle stands apart.
    """
    written = ""
    for index, syllable in enumerate(syllables):
        if index and written:
            if index in breaks:
                written += " "
            elif (
                syllable.lower().translate(_TONE_MARK_FOLD).startswith(_APOSTROPHE_INITIALS)
                and written[-1].isalpha()
            ):
                written += "'"
        written += syllable
    return written


def _word_breaks(
    pieces: List[str], han_flags: Tuple[bool, ...], particle_last: bool
) -> frozenset[int]:
    """Piece indices that start a new written word."""
    breaks = {i for i in range(1, len(pieces)) if not han_flags[i] or not han_flags[i - 1]}
    if particle_last:
        breaks.add(len(pieces) - 1)
    if JIEBA_AVAILABLE:
        # Segment each Han run; a phrase-length translation is several words.
        start = 0
        while start < len(pieces):
            if not han_flags[start]:
                start += 1
                continue
            end = start
            while end < len(pieces) and han_flags[end]:
                end += 1
            offset = start
            for segment in jieba.cut("".join(pieces[start:end]), cut_all=False):
                if offset != start:
                    breaks.add(offset)
                offset += len(segment)
            start = end
    return frozenset(breaks)


def _settled_by_phrase(text: str, index: int) -> bool:
    """Whether a pypinyin phrase of 2+ characters covers ``text[index]``."""
    for start in range(0, index + 1):
        for end in range(index + 1, len(text) + 1):
            if end - start >= 2 and text[start:end] in _PHRASES_DICT:
                return True
    return False


def word_reading(chinese_text: str, override: Optional[str] = None) -> Optional[WordReading]:
    """Return the reading of one dictionary word, or None when there is none.

    *override* is the lemma's ``pinyin`` grammar fact: tone-marked syllables
    separated by spaces, one per Han character ("zhǎng").  It is used when its
    syllable count matches the word and ignored (with a warning) otherwise, so
    a stale override cannot misalign the characters.

    Readings are citation tones: no 一/不 tone sandhi, neutral tone left
    unmarked (的 -> "de").  Traditional characters are read through their
    simplified forms, as in :func:`generate_pinyin`.
    """
    if not chinese_text or not is_chinese(chinese_text):
        return None
    text = to_simplified(chinese_text.strip())
    pieces = _split_runs(text)
    han_indices = [i for i, piece in enumerate(pieces) if _HAN_CHAR.match(piece)]
    han_flags = tuple(bool(_HAN_CHAR.match(piece)) for piece in pieces)
    particle_last = len(han_indices) > 1 and pieces[-1] == _ATTRIBUTIVE_SUFFIX

    if override:
        override_syllables = override.split()
        if len(override_syllables) == len(han_indices):
            syllables = list(pieces)
            for position, syllable in zip(han_indices, override_syllables):
                syllables[position] = syllable
            frozen = tuple(syllables)
            breaks = _word_breaks(pieces, han_flags, particle_last)
            return WordReading(frozen, _join_word(frozen, breaks), (), "override")
        logger.warning(
            "Ignoring pinyin override %r for %r: %d syllables for %d characters",
            override,
            chinese_text,
            len(override_syllables),
            len(han_indices),
        )

    if not PYPINYIN_AVAILABLE:
        return None
    han_text = "".join(pieces[i] for i in han_indices)
    try:
        readings = lazy_pinyin(han_text, style=Style.TONE)
    except Exception as exc:  # pragma: no cover - pypinyin failure
        logger.warning("Failed to generate pinyin for %r: %s", chinese_text, exc)
        return None
    if len(readings) != len(han_indices):
        return None

    syllables = list(pieces)
    ambiguous: List[int] = []
    for han_position, (piece_index, reading) in enumerate(zip(han_indices, readings)):
        if particle_last and piece_index == len(pieces) - 1:
            syllables[piece_index] = "de"
            continue
        syllables[piece_index] = reading
        char = pieces[piece_index]
        if char not in COMMON_POLYPHONES:
            continue
        candidates = _pinyin_table(char, style=Style.TONE, heteronym=True)[0]
        if len(set(candidates)) > 1 and not _settled_by_phrase(han_text, han_position):
            ambiguous.append(piece_index)
    frozen = tuple(syllables)
    breaks = _word_breaks(pieces, han_flags, particle_last)
    return WordReading(frozen, _join_word(frozen, breaks), tuple(ambiguous), "pypinyin")


def generate_pinyin_sort_key(chinese_text: str) -> Optional[str]:
    """
    Generate a pinyin sort key for Chinese dictionary ordering.

    Unlike :func:`generate_pinyin`, tones are written as trailing digits rather
    than diacritics (e.g. "dian3" instead of "diǎn").  Tone-marked vowels live
    far above ASCII in Unicode, so a byte-ordered comparison of tone-marked
    pinyin sorts by tone before it sorts by spelling.  Trailing digits keep the
    letters adjacent, so a plain BINARY collation yields standard dictionary
    order: alphabetical by syllable first, then tone 1-4 within a homophone.

    Neutral tone is written as 5 so that every syllable ends in a digit, and it
    sorts after the four marked tones as dictionaries expect.  ü is rendered
    "v" (pypinyin's convention), which sorts just after "u".

    Args:
        chinese_text: Chinese text to convert (simplified or traditional)

    Returns:
        Lowercase pinyin with tone digits (e.g., "ni3 hao3"), or None if:
        - pypinyin is not available
        - text is empty
        - text doesn't contain Chinese characters
    """
    if not PYPINYIN_AVAILABLE or not chinese_text:
        return None

    if not is_chinese(chinese_text):
        return None

    try:
        # Convert to simplified Chinese first for better pinyin accuracy
        # pypinyin handles simplified characters more reliably for polyphonic chars
        text_for_pinyin = to_simplified(chinese_text)

        pinyin_list = lazy_pinyin(text_for_pinyin, style=Style.TONE3, neutral_tone_with_five=True)
        return " ".join(pinyin_list).lower()
    except Exception as e:
        logger.warning(f"Failed to generate pinyin sort key for '{chinese_text}': {e}")
        return None


def generate_pinyin_ruby_html(chinese_text: str) -> str:
    """
    Generate HTML with ruby annotations for Chinese text with Pinyin.

    This creates elegant ruby text similar to Japanese furigana, with Pinyin
    displayed above each Chinese word (using jieba segmentation) or character.

    For better accuracy with polyphonic characters (多音字), the text is first
    converted to simplified Chinese for pinyin generation, while the original
    characters are preserved in the ruby annotation display.

    Args:
        chinese_text: Chinese text to annotate with pinyin (simplified or traditional)

    Returns:
        HTML string with <ruby> tags, or plain text if:
        - pypinyin is not available
        - text doesn't contain Chinese characters

    Example:
        Input: "你好世界"
        Output: '<ruby>你好<rt>nǐ hǎo</rt></ruby><ruby>世界<rt>shì jiè</rt></ruby>'

    Note:
        Pinyin is generated at the word level using pypinyin's contextual awareness,
        so compound words get their correct pronunciations (e.g., 会计 → kuàijì).
    """
    if not PYPINYIN_AVAILABLE or not chinese_text:
        return chinese_text

    # Only generate ruby text if text contains Chinese characters
    if not is_chinese(chinese_text):
        return chinese_text

    try:
        result = []

        # Convert to simplified for pinyin generation (better accuracy)
        simplified_text = to_simplified(chinese_text)

        if JIEBA_AVAILABLE:
            # Use jieba to segment both texts into words
            # Segment simplified for pinyin, but display original characters
            original_segments = list(jieba.cut(chinese_text, cut_all=False))
            simplified_segments = list(jieba.cut(simplified_text, cut_all=False))

            # If segmentation lengths differ, fall back to using original text directly
            if len(original_segments) != len(simplified_segments):
                simplified_segments = original_segments

            for orig_segment, simp_segment in zip(original_segments, simplified_segments):
                if is_chinese(orig_segment):
                    # Get pinyin from simplified segment for better accuracy
                    pinyin_list = lazy_pinyin(simp_segment, style=Style.TONE)
                    if pinyin_list:
                        pinyin = " ".join(pinyin_list)
                        # Display original characters with pinyin from simplified
                        result.append(f"<ruby>{orig_segment}<rt>{pinyin}</rt></ruby>")
                    else:
                        result.append(wrap_unannotated_ruby(orig_segment))
                else:
                    # Non-Chinese segment (Latin word, punctuation, space, etc.)
                    # Still wrapped so it shares a baseline with annotated neighbours.
                    result.append(wrap_unannotated_ruby(orig_segment))
        else:
            # Fallback to character-by-character if jieba is not available
            for orig_char, simp_char in zip(chinese_text, simplified_text):
                if is_chinese(orig_char):
                    # Get pinyin from simplified character for better accuracy
                    pinyin_list = lazy_pinyin(simp_char, style=Style.TONE)
                    if pinyin_list:
                        pinyin = pinyin_list[0]
                        result.append(f"<ruby>{orig_char}<rt>{pinyin}</rt></ruby>")
                    else:
                        result.append(wrap_unannotated_ruby(orig_char))
                else:
                    # Non-Chinese character (Latin letter, punctuation, space, etc.)
                    result.append(wrap_unannotated_ruby(orig_char))

        return "".join(result)
    except Exception as e:
        logger.warning(f"Failed to generate ruby HTML for '{chinese_text}': {e}")
        return chinese_text
