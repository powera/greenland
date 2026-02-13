"""Kannada-specific utility functions."""

import unicodedata
from typing import List


def remove_vowel_signs(text: str) -> str:
    """
    Remove optional vowel signs / accent marks from Kannada text.

    Kannada script (U+0C80-U+0CFF) uses combining marks for vowel signs
    (matras) attached to consonants.  This function strips only
    non-essential diacritics (accent marks, stress marks) while preserving
    the core Kannada characters.

    Marks that are preserved:
    - U+0CBE-U+0CCC: vowel signs (matras) -- integral to syllable formation
    - U+0CCD: virama (halant) -- essential for conjuncts
    - U+0CBC: nukta

    Marks that are removed:
    - U+0951: DEVANAGARI STRESS SIGN UDATTA (sometimes used in Vedic texts)
    - U+0952: DEVANAGARI STRESS SIGN ANUDATTA
    - U+0300: COMBINING GRAVE ACCENT
    - U+0301: COMBINING ACUTE ACCENT

    Args:
        text: Kannada text possibly containing extra diacritical marks

    Returns:
        Text with accent/stress marks removed but Kannada characters preserved
    """
    stress_marks = {"\u0300", "\u0301", "\u0951", "\u0952"}

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


def normalize_kannada_text(text: str) -> str:
    """
    Normalize Kannada text: remove stray accent marks and normalize to NFC.

    Args:
        text: Text that may have accent marks and various Unicode representations

    Returns:
        Normalized text without accent marks
    """
    return remove_vowel_signs(text)


def clean_form(text: str) -> List[str]:
    """
    Clean a Kannada grammatical form by removing accent marks and handling alternatives.

    Args:
        text: Raw form text (may contain accent marks, slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013"):  # dash, em-dash, en-dash
        return []

    # Split by slash to handle alternative forms
    forms = [f.strip() for f in text.split("/")]

    # Remove accent marks from each form
    cleaned_forms = [remove_vowel_signs(form) for form in forms]

    # Filter out empty strings
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms
