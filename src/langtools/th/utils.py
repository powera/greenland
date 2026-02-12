"""Thai-specific utility functions for text processing.

Thai script has unique characteristics:
- No spaces between words (spaces appear between clauses/sentences)
- Tone marks and vowel markers are combining characters above/below consonants
- Thai digits (๐-๙) may appear alongside Arabic digits (0-9)
"""

import re
import unicodedata
from typing import List

# Thai Unicode ranges
_THAI_CONSONANTS = set("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")
_THAI_VOWELS = set("ะัาำิีึืุูเแโใไ็")
_THAI_TONE_MARKS = set("่้๊๋")
_THAI_DIGITS = set("๐๑๒๓๔๕๖๗๘๙")
_ARABIC_DIGIT_FOR_THAI = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def normalize_thai_text(text: str) -> str:
    """Normalize Thai text to NFC and clean up whitespace.

    - Normalizes Unicode to NFC (composed form)
    - Collapses multiple spaces to single space
    - Strips leading/trailing whitespace

    Args:
        text: Raw Thai text

    Returns:
        Normalized text
    """
    normalized = unicodedata.normalize("NFC", text)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def thai_digits_to_arabic(text: str) -> str:
    """Convert Thai digits (๐-๙) to Arabic digits (0-9).

    Args:
        text: Text possibly containing Thai digits

    Returns:
        Text with Thai digits replaced by Arabic digits
    """
    return text.translate(_ARABIC_DIGIT_FOR_THAI)


def contains_thai(text: str) -> bool:
    """Check whether a string contains any Thai script characters.

    Args:
        text: Text to check

    Returns:
        True if the text contains Thai consonants, vowels, or tone marks
    """
    thai_chars = _THAI_CONSONANTS | _THAI_VOWELS | _THAI_TONE_MARKS
    return any(ch in thai_chars for ch in text)


def clean_form(text: str) -> List[str]:
    """Clean a Thai grammatical form and handle alternatives.

    Args:
        text: Raw form text (may contain slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013"):
        return []

    forms = [f.strip() for f in text.split("/")]
    cleaned_forms = [normalize_thai_text(form) for form in forms]
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms
