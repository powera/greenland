#!/usr/bin/env python3
"""
Chinese character conversion utilities.

This module provides functions to convert between Traditional and Simplified Chinese.
The wordfreq database stores Chinese translations in Traditional characters,
and this utility converts them to Simplified when needed for export/display.
"""

import logging
from typing import Optional

try:
    from opencc import OpenCC

    OPENCC_AVAILABLE = True
except ImportError:
    OPENCC_AVAILABLE = False

logger = logging.getLogger(__name__)

# Lazy-loaded converters
_traditional_to_simplified = None
_simplified_to_traditional = None


def _get_t2s_converter() -> Optional[OpenCC]:
    """Get or create Traditional to Simplified converter."""
    global _traditional_to_simplified

    if not OPENCC_AVAILABLE:
        logger.warning(
            "opencc-python-reimplemented not installed. Cannot convert Chinese characters."
        )
        return None

    if _traditional_to_simplified is None:
        try:
            # t2s = Traditional Chinese to Simplified Chinese
            _traditional_to_simplified = OpenCC("t2s")
        except Exception as e:
            logger.error(f"Failed to initialize Traditional to Simplified converter: {e}")
            return None

    return _traditional_to_simplified


def _get_s2t_converter() -> Optional[OpenCC]:
    """Get or create Simplified to Traditional converter."""
    global _simplified_to_traditional

    if not OPENCC_AVAILABLE:
        logger.warning(
            "opencc-python-reimplemented not installed. Cannot convert Chinese characters."
        )
        return None

    if _simplified_to_traditional is None:
        try:
            # s2t = Simplified Chinese to Traditional Chinese
            _simplified_to_traditional = OpenCC("s2t")
        except Exception as e:
            logger.error(f"Failed to initialize Simplified to Traditional converter: {e}")
            return None

    return _simplified_to_traditional


def to_simplified(text: str) -> str:
    """
    Convert Traditional Chinese text to Simplified Chinese.

    Args:
        text: Traditional Chinese text (or mixed text)

    Returns:
        Simplified Chinese text. If conversion fails or library is unavailable,
        returns the original text.
    """
    if not text:
        return text

    converter = _get_t2s_converter()
    if converter is None:
        return text

    try:
        return converter.convert(text)
    except Exception as e:
        logger.error(f"Failed to convert to simplified: {text} - {e}")
        return text


def to_traditional(text: str) -> str:
    """
    Convert Simplified Chinese text to Traditional Chinese.

    Args:
        text: Simplified Chinese text (or mixed text)

    Returns:
        Traditional Chinese text. If conversion fails or library is unavailable,
        returns the original text.
    """
    if not text:
        return text

    converter = _get_s2t_converter()
    if converter is None:
        return text

    try:
        return converter.convert(text)
    except Exception as e:
        logger.error(f"Failed to convert to traditional: {text} - {e}")
        return text


def get_chinese_translation(lemma, simplified: bool = False) -> Optional[str]:
    """
    Get Chinese translation from a lemma object.

    Args:
        lemma: Lemma object with chinese_translation field (stored as Traditional)
        simplified: If True, convert to Simplified Chinese; if False, return Traditional

    Returns:
        Chinese translation in requested form, or None if not available
    """
    if not hasattr(lemma, "chinese_translation") or not lemma.chinese_translation:
        return None

    traditional = lemma.chinese_translation

    if simplified:
        return to_simplified(traditional)
    else:
        return traditional


# Example usage and testing
if __name__ == "__main__":
    # Test conversions
    test_cases = [
        ("傳統", "Traditional word"),
        ("簡化", "Simplified should stay mostly the same"),
        ("雞", "Traditional chicken"),
        ("鸡", "Simplified chicken"),
        ("葡萄酒", "Wine (grape wine)"),
    ]

    print("Traditional to Simplified conversions:")
    for text, description in test_cases:
        result = to_simplified(text)
        print(f"  {text} → {result} ({description})")

    print("\nSimplified to Traditional conversions:")
    for text, description in test_cases:
        result = to_traditional(text)
        print(f"  {text} → {result} ({description})")
