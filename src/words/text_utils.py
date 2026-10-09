"""Text utility functions for wordfreq processing.

This module provides utility functions for text analysis and validation,
including numeral detection and text normalization.
"""

import re


def is_numeral(text: str) -> bool:
    """
    Check if a string is primarily a numeral or numeral variant.

    Args:
        text: The text to check

    Returns:
        True if the text is a numeral (e.g., "1000", "42", "1K", "4th"), False otherwise

    Examples:
        >>> is_numeral("1000")
        True
        >>> is_numeral("42")
        True
        >>> is_numeral("1K")
        True
        >>> is_numeral("4th")
        True
        >>> is_numeral("thousand")
        False
        >>> is_numeral("street")
        False
    """
    if not text:
        return False

    # Strip whitespace
    text = text.strip()

    # Check if it's purely digits
    if text.isdigit():
        return True

    # Check if it's a number with common separators (1,000 or 1.000)
    if re.match(r"^[\d,.\s]+$", text):
        return True

    # Check for abbreviated numbers with K/M/B suffix (1K, 2.5M, etc.)
    if re.match(r"^\d+[.,]?\d*[KMBkmb]$", text):
        return True

    # Check for ordinal numbers (1st, 2nd, 3rd, 4th, etc.)
    if re.match(r"^\d+(st|nd|rd|th)$", text, re.IGNORECASE):
        return True

    return False
