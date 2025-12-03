#!/usr/bin/env python3
"""
Pinyin helper module for converting Chinese text to Pinyin.

This module provides utilities for generating Pinyin transliterations
with graceful degradation if pypinyin is not available.
"""

import re
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Try to import pypinyin, gracefully handle if not available
try:
    from pypinyin import lazy_pinyin, Style

    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False
    logger.warning("pypinyin not available - Chinese pinyin transliteration will be disabled")

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

    Args:
        chinese_text: Chinese text to convert to pinyin

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
        # Use Style.TONE to get pinyin with tone marks (e.g., "nǐ hǎo")
        pinyin_list = lazy_pinyin(chinese_text, style=Style.TONE)
        return " ".join(pinyin_list)
    except Exception as e:
        logger.warning(f"Failed to generate pinyin for '{chinese_text}': {e}")
        return None


def generate_pinyin_ruby_html(chinese_text: str) -> str:
    """
    Generate HTML with ruby annotations for Chinese text with Pinyin.

    This creates elegant ruby text similar to Japanese furigana, with Pinyin
    displayed above each Chinese word (using jieba segmentation) or character.

    Args:
        chinese_text: Chinese text to annotate with pinyin

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

        if JIEBA_AVAILABLE:
            # Use jieba to segment text into words for better readability
            segments = jieba.cut(chinese_text, cut_all=False)

            for segment in segments:
                if is_chinese(segment):
                    # Get pinyin at word level for correct pronunciation
                    pinyin_list = lazy_pinyin(segment, style=Style.TONE)
                    if pinyin_list:
                        pinyin = " ".join(pinyin_list)
                        result.append(f"<ruby>{segment}<rt>{pinyin}</rt></ruby>")
                    else:
                        result.append(segment)
                else:
                    # Non-Chinese segment (punctuation, space, etc.)
                    result.append(segment)
        else:
            # Fallback to character-by-character if jieba is not available
            for char in chinese_text:
                if is_chinese(char):
                    # Get pinyin for this character
                    pinyin_list = lazy_pinyin(char, style=Style.TONE)
                    if pinyin_list:
                        pinyin = pinyin_list[0]
                        result.append(f"<ruby>{char}<rt>{pinyin}</rt></ruby>")
                    else:
                        result.append(char)
                else:
                    # Non-Chinese character (punctuation, space, etc.)
                    result.append(char)

        return "".join(result)
    except Exception as e:
        logger.warning(f"Failed to generate ruby HTML for '{chinese_text}': {e}")
        return chinese_text
