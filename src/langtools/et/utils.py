"""Estonian-specific utility functions."""

import unicodedata
from typing import List


def remove_stress_marks(text: str) -> str:
    """
    Remove stress/accent marks from Estonian text while preserving Estonian letters.

    Estonian uses standard Latin letters plus the following special characters:
    - š, ž (caron — foreign loanwords, but part of the alphabet)
    - ä, ö, ü, õ (umlauts and tilde-o — core Estonian vowels)

    Stress marks (acute, grave) that may appear on vowels for
    pronunciation guidance are removed.

    Args:
        text: Text with possible stress marks

    Returns:
        Text without stress marks but with Estonian letters preserved
    """
    # Stress/tone combining marks that should be REMOVED
    # U+0300: COMBINING GRAVE ACCENT
    # U+0301: COMBINING ACUTE ACCENT
    # Note: U+0303 (COMBINING TILDE) must be preserved — it forms õ
    # Note: U+030C (COMBINING CARON) must be preserved — it forms š, ž
    # Note: U+0308 (COMBINING DIAERESIS) must be preserved — it forms ä, ö, ü
    stress_marks = {"\u0300", "\u0301"}

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


def normalize_estonian_text(text: str) -> str:
    """
    Normalize Estonian text: remove stress marks and normalize to NFC.

    Args:
        text: Text that may have stress marks and various Unicode representations

    Returns:
        Normalized text without stress marks
    """
    return remove_stress_marks(text)


def clean_form(text: str) -> List[str]:
    """
    Clean an Estonian grammatical form by removing stress marks and handling alternatives.

    Args:
        text: Raw form text (may contain stress marks, slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in (
        "",
        "-",
        "\u2014",
        "\u2013",
    ):  # dash, em-dash, en-dash
        return []

    # Split by slash to handle alternative forms
    forms = [f.strip() for f in text.split("/")]

    # Remove stress marks from each form
    cleaned_forms = [remove_stress_marks(form) for form in forms]

    # Filter out empty strings
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms
