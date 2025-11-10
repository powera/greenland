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
    return bool(re.search(r'[\u4e00-\u9fff]', text))


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
        return ' '.join(pinyin_list)
    except Exception as e:
        logger.warning(f"Failed to generate pinyin for '{chinese_text}': {e}")
        return None


def generate_pinyin_ruby_html(chinese_text: str) -> str:
    """
    Generate HTML with ruby annotations for Chinese text with Pinyin.

    This creates elegant ruby text similar to Japanese furigana, with Pinyin
    displayed above each Chinese character.

    Args:
        chinese_text: Chinese text to annotate with pinyin

    Returns:
        HTML string with <ruby> tags, or plain text if:
        - pypinyin is not available
        - text doesn't contain Chinese characters

    Example:
        Input: "你好"
        Output: '<ruby>你<rt>nǐ</rt></ruby><ruby>好<rt>hǎo</rt></ruby>'
    """
    if not PYPINYIN_AVAILABLE or not chinese_text:
        return chinese_text

    # Only generate ruby text if text contains Chinese characters
    if not is_chinese(chinese_text):
        return chinese_text

    try:
        # Generate pinyin for each character separately
        result = []
        for char in chinese_text:
            if is_chinese(char):
                # Get pinyin for this character
                pinyin_list = lazy_pinyin(char, style=Style.TONE)
                if pinyin_list:
                    pinyin = pinyin_list[0]
                    result.append(f'<ruby>{char}<rt>{pinyin}</rt></ruby>')
                else:
                    result.append(char)
            else:
                # Non-Chinese character (punctuation, space, etc.)
                result.append(char)

        return ''.join(result)
    except Exception as e:
        logger.warning(f"Failed to generate ruby HTML for '{chinese_text}': {e}")
        return chinese_text
