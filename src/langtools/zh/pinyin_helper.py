#!/usr/bin/env python3
"""
Pinyin helper module for Chinese text romanization.

This module provides utilities for generating pinyin transliterations
for Chinese text. Degrades gracefully if required libraries are not available.
"""

import logging
import re
from typing import Optional

from langtools.ruby_html import wrap_unannotated_ruby

logger = logging.getLogger(__name__)

# Try to import pypinyin, gracefully handle if not available
try:
    from pypinyin import Style, lazy_pinyin

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
