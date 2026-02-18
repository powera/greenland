"""Ukrainian-specific utility functions."""

import unicodedata
from typing import List


def remove_stress_marks(text: str) -> str:
    """
    Remove stress/accent marks from Ukrainian text while preserving Ukrainian letters.

    Ukrainian uses the Cyrillic script with these specific letters:
    - Standard Ukrainian Cyrillic: А-Я, а-я (minus some Russian-only letters)
    - Ukrainian-specific: Ґ (ґ), Є (є), І (і), Ї (ї)

    Stress marks (acute accent U+0301) may appear on vowels for
    pronunciation guidance and should be removed.

    Args:
        text: Text with possible stress marks

    Returns:
        Text without stress marks but with Ukrainian letters preserved
    """
    # Stress/tone combining marks that should be REMOVED
    # U+0300: COMBINING GRAVE ACCENT
    # U+0301: COMBINING ACUTE ACCENT (most common stress mark in Ukrainian)
    # U+0303: COMBINING TILDE
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


def normalize_ukrainian_text(text: str) -> str:
    """
    Normalize Ukrainian text: remove stress marks and normalize to NFC.

    Args:
        text: Text that may have stress marks and various Unicode representations

    Returns:
        Normalized text without stress marks
    """
    return remove_stress_marks(text)


def clean_form(text: str) -> List[str]:
    """
    Clean a Ukrainian grammatical form by removing stress marks and handling alternatives.

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
    cleaned_forms = [remove_stress_marks(form) for form in forms]

    # Filter out empty strings
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms

def strip_subject_pronoun(text: str) -> str:
    """Strip a Ukrainian subject pronoun from the beginning of a verb phrase."""
    normalized = normalize_ukrainian_text(text.strip().lower())
    if not normalized:
        return ""

    combined_pronouns = ["він/вона ", "вона/він ", "він / вона ", "вона / він "]
    for pronoun in combined_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun):].strip()

    pronouns = ["я ", "ти ", "він ", "вона ", "воно ", "ми ", "ви ", "вони "]
    for pronoun in pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun):].strip()
    return normalized

