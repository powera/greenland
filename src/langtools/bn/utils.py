"""Bengali-specific utility functions."""

import unicodedata
from typing import List


def remove_nukta_marks(text: str) -> str:
    """
    Remove nukta (নুক্তা) combining marks from Bengali text.

    The nukta (U+09BC) is sometimes used in Bengali to represent
    borrowed sounds (e.g., from Arabic/Persian).  This function
    strips those marks while preserving all standard Bengali characters.

    Args:
        text: Text with possible nukta marks

    Returns:
        Text without nukta marks
    """
    # U+09BC: BENGALI SIGN NUKTA
    return text.replace("\u09bc", "")


def normalize_bengali_text(text: str) -> str:
    """
    Normalize Bengali text to NFC and strip extraneous whitespace.

    Bengali text can arrive in different Unicode normalization forms
    (NFD vs NFC).  This function ensures consistent NFC representation
    and removes nukta marks used only for transliteration purposes.

    Args:
        text: Raw Bengali text

    Returns:
        Normalized text in NFC form
    """
    normalized = unicodedata.normalize("NFC", text)
    return normalized.strip()


def clean_form(text: str) -> List[str]:
    """
    Clean a Bengali grammatical form by normalizing and handling alternatives.

    Args:
        text: Raw form text (may contain slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013"):  # dash, em-dash, en-dash
        return []

    # Split by slash to handle alternative forms
    forms = [f.strip() for f in text.split("/")]

    # Normalize each form
    cleaned_forms = [normalize_bengali_text(form) for form in forms]

    # Filter out empty strings
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms


def is_bengali_script(text: str) -> bool:
    """
    Check whether a string contains Bengali (Eastern Nagari) script characters.

    Args:
        text: Text to check

    Returns:
        True if the text contains at least one Bengali script character
    """
    for char in text:
        if "\u0980" <= char <= "\u09ff":
            return True
    return False
