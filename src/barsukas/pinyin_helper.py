#!/usr/bin/env python3
"""
Pinyin and Romaji helper module for CJK text romanization.

This module provides utilities for generating:
- Pinyin transliterations for Chinese text
- Romaji transliterations for Japanese text

Both degrade gracefully if required libraries are not available.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import pypinyin, gracefully handle if not available
try:
    from pypinyin import Style, lazy_pinyin

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

# Try to import pykakasi for Japanese romaji, gracefully handle if not available
try:
    import pykakasi

    PYKAKASI_AVAILABLE = True
    # Create a singleton kakasi instance for performance
    _kakasi = pykakasi.kakasi()
except ImportError:
    PYKAKASI_AVAILABLE = False
    _kakasi = None
    logger.warning("pykakasi not available - Japanese romaji transliteration will be disabled")


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


def is_japanese(text: str) -> bool:
    """
    Check if the text contains Japanese characters (hiragana, katakana, or kanji).

    Args:
        text: Text to check

    Returns:
        True if text contains Japanese characters, False otherwise
    """
    if not text:
        return False
    # Check for Hiragana, Katakana, or CJK (kanji) ranges
    # Hiragana: U+3040-U+309F
    # Katakana: U+30A0-U+30FF
    # CJK Unified Ideographs: U+4E00-U+9FFF (shared with Chinese)
    return bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]", text))


def generate_romaji(japanese_text: str) -> Optional[str]:
    """
    Generate romaji for Japanese text.

    Args:
        japanese_text: Japanese text to convert to romaji

    Returns:
        Romaji string, or None if:
        - pykakasi is not available
        - text is empty
        - text doesn't contain Japanese characters
    """
    if not PYKAKASI_AVAILABLE or not japanese_text or _kakasi is None:
        return None

    # Only generate romaji if text actually contains Japanese characters
    if not is_japanese(japanese_text):
        return None

    try:
        result = _kakasi.convert(japanese_text)
        # Join the romaji parts with spaces
        romaji_parts = [item["hepburn"] for item in result]
        return " ".join(romaji_parts)
    except Exception as e:
        logger.warning(f"Failed to generate romaji for '{japanese_text}': {e}")
        return None


def generate_romaji_ruby_html(japanese_text: str) -> str:
    """
    Generate HTML with ruby annotations for Japanese text with romaji.

    This creates elegant ruby text with romaji displayed above each
    Japanese word/segment.

    Args:
        japanese_text: Japanese text to annotate with romaji

    Returns:
        HTML string with <ruby> tags, or plain text if:
        - pykakasi is not available
        - text doesn't contain Japanese characters

    Example:
        Input: "東京"
        Output: '<ruby>東京<rt>toukyou</rt></ruby>'
    """
    if not PYKAKASI_AVAILABLE or not japanese_text or _kakasi is None:
        return japanese_text

    # Only generate ruby text if text contains Japanese characters
    if not is_japanese(japanese_text):
        return japanese_text

    try:
        result = _kakasi.convert(japanese_text)
        html_parts = []

        for item in result:
            orig = item["orig"]
            romaji = item["hepburn"]

            # Only add ruby if the original differs from romaji (i.e., it's Japanese)
            # and the romaji is not empty
            if orig != romaji and romaji:
                html_parts.append(f"<ruby>{orig}<rt>{romaji}</rt></ruby>")
            else:
                html_parts.append(orig)

        return "".join(html_parts)
    except Exception as e:
        logger.warning(f"Failed to generate romaji ruby HTML for '{japanese_text}': {e}")
        return japanese_text
