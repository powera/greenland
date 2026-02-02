"""Generic utility functions for Wiktionary parsing.

Language-specific utilities are in langtools/<lang>/utils.py
"""

import unicodedata
from typing import Callable, List


def normalize_text(text: str) -> str:
    """
    Normalize text to NFC form for consistent comparison.

    Args:
        text: Text that may have various Unicode representations

    Returns:
        NFC-normalized text
    """
    return unicodedata.normalize("NFC", text)


def clean_form_generic(
    text: str,
    normalizer: Callable[[str], str] = normalize_text,
) -> List[str]:
    """
    Clean a grammatical form by handling alternatives.

    This is a generic version that can be customized with a language-specific
    normalizer function.

    Args:
        text: Raw form text (may contain slashes for alternatives, etc.)
        normalizer: Function to normalize/clean each form

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013"):  # dash, em-dash, en-dash
        return []

    # Split by slash to handle alternative forms
    forms = [f.strip() for f in text.split("/")]

    # Normalize each form
    cleaned_forms = [normalizer(form) for form in forms]

    # Filter out empty strings
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms


def extract_primary_form(forms: List[str]) -> str:
    """
    Extract the primary (first) form from a list of alternative forms.

    Args:
        forms: List of forms where first is primary

    Returns:
        Primary form or empty string if no forms
    """
    return forms[0] if forms else ""


def extract_alternative_forms(forms: List[str]) -> List[str]:
    """
    Extract alternative forms (all but first) from a list of forms.

    Args:
        forms: List of forms where first is primary

    Returns:
        List of alternative forms (may be empty)
    """
    return forms[1:] if len(forms) > 1 else []


def is_placeholder_text(text: str) -> bool:
    """
    Check if text is a placeholder indicating no form exists.

    Args:
        text: Text to check

    Returns:
        True if this is a placeholder (dash, empty, etc.)
    """
    placeholders = {"", "-", "\u2014", "\u2013", "\u2212", "N/A", "n/a", "none", "None"}
    return text.strip() in placeholders
