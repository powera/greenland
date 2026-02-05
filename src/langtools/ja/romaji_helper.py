#!/usr/bin/env python3
"""
Romaji helper module for Japanese text romanization.

This module provides utilities for generating romaji transliterations
for Japanese text. Degrades gracefully if pykakasi is not available.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try to import pykakasi for Japanese romaji, gracefully handle if not available
_kakasi: Any = None
try:
    import pykakasi

    PYKAKASI_AVAILABLE = True
    # Create a singleton kakasi instance for performance
    _kakasi = pykakasi.kakasi()
except ImportError:
    PYKAKASI_AVAILABLE = False
    logger.warning("pykakasi not available - Japanese romaji transliteration will be disabled")


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


def generate_hiragana(japanese_text: str) -> Optional[str]:
    """
    Generate hiragana reading for Japanese text (for dictionary sort keys).

    Args:
        japanese_text: Japanese text to convert to hiragana

    Returns:
        Hiragana string, or None if pykakasi is not available or text
        doesn't contain Japanese characters.
    """
    if not PYKAKASI_AVAILABLE or not japanese_text or _kakasi is None:
        return None

    if not is_japanese(japanese_text):
        return None

    try:
        result = _kakasi.convert(japanese_text)
        hira_parts = [item["hira"] for item in result]
        return "".join(hira_parts)
    except Exception as e:
        logger.warning(f"Failed to generate hiragana for '{japanese_text}': {e}")
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
