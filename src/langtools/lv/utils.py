"""Latvian-specific utility functions."""

import unicodedata
from typing import List


def remove_long_mark_stress(text: str) -> str:
    """
    Remove stress/accent marks from Latvian text while preserving Latvian letters.

    Latvian has distinct letters with diacritics that must be preserved:
    - Macrons: ā, ē, ī, ū (long vowels — integral to the language)
    - Cedillas: ģ, ķ, ļ, ņ (palatalized consonants)
    - Caron: č, š, ž (fricatives/affricates)

    Stress marks (acute, grave, tilde) that may appear on vowels for
    pronunciation guidance are removed.

    Args:
        text: Text with possible stress marks

    Returns:
        Text without stress marks but with Latvian letters preserved
    """
    # Stress/tone combining marks that should be REMOVED
    # U+0300: COMBINING GRAVE ACCENT
    # U+0301: COMBINING ACUTE ACCENT
    # U+0303: COMBINING TILDE
    # Note: U+0304 (COMBINING MACRON) must be preserved — it forms ā, ē, ī, ū
    # Note: U+030C (COMBINING CARON) must be preserved — it forms č, š, ž
    # Note: U+0327 (COMBINING CEDILLA) must be preserved — it forms ģ, ķ, ļ, ņ
    stress_marks = {"\u0300", "\u0301", "\u0303"}

    decomposed = unicodedata.normalize("NFD", text)

    result: List[str] = []
    i = 0
    while i < len(decomposed):
        char = decomposed[i]

        if unicodedata.category(char) != "Mn":
            base = char
            combining_marks: List[str] = []

            j = i + 1
            while j < len(decomposed) and unicodedata.category(decomposed[j]) == "Mn":
                combining_marks.append(decomposed[j])
                j += 1

            non_stress_marks: List[str] = [m for m in combining_marks if m not in stress_marks]

            reconstructed = unicodedata.normalize("NFC", base + "".join(non_stress_marks))
            result.append(reconstructed)
            i = j
        else:
            if char not in stress_marks:
                result.append(char)
            i += 1

    return "".join(result)


def normalize_latvian_text(text: str) -> str:
    """
    Normalize Latvian text: remove stress marks and normalize to NFC.

    Args:
        text: Text that may have stress marks and various Unicode representations

    Returns:
        Normalized text without stress marks
    """
    return remove_long_mark_stress(text)


def clean_form(text: str) -> List[str]:
    """
    Clean a Latvian grammatical form by removing stress marks and handling alternatives.

    Args:
        text: Raw form text (may contain stress marks, slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013"):  # dash, em-dash, en-dash
        return []

    # Split by slash to handle alternative forms
    forms = [f.strip() for f in text.split("/")]

    # Remove stress marks from each form
    cleaned_forms = [remove_long_mark_stress(form) for form in forms]

    # Filter out empty strings
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms
