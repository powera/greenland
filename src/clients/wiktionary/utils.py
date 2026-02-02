"""Utility functions for Wiktionary parsing."""

import unicodedata
from typing import List


def remove_stress_marks(text: str) -> str:
    """
    Remove stress/accent marks from Lithuanian text while preserving Lithuanian letters.

    Lithuanian has distinct letters with diacritics (a, c, e, e, i, s, u, u, z)
    that must be preserved. However, stress marks (acute, grave, tilde)
    that can appear on ANY vowel for pronunciation are removed.

    Complex case: stress marks can appear on top of Lithuanian letters (e.g., u with ogonek + tilde)
    In this case, we need to preserve the Lithuanian letter (u with ogonek) but remove the stress (tilde).

    Args:
        text: Text with stress marks

    Returns:
        Text without stress marks but with Lithuanian letters preserved
    """
    # Stress/tone combining marks that should be REMOVED
    # U+0300: COMBINING GRAVE ACCENT
    # U+0301: COMBINING ACUTE ACCENT
    # U+0303: COMBINING TILDE
    # Note: U+0307 (COMBINING DOT ABOVE) has dual purpose:
    #       - On 'e' or 'E': forms Lithuanian e with dot (must be preserved)
    #       - On other vowels: stress/accent mark (must be removed)
    # Note: U+030C (COMBINING CARON) is NOT a stress mark - it's part of c, s, z
    # Note: U+0304 (COMBINING MACRON) is NOT a stress mark - it's part of u with macron
    # Note: U+0328 (COMBINING OGONEK) is NOT a stress mark - it's part of a, e, i, u with ogonek
    stress_marks = {"\u0300", "\u0301", "\u0303"}

    # Decompose unicode characters into base + combining marks
    # NFD = Canonical Decomposition
    decomposed = unicodedata.normalize("NFD", text)

    # Build result by filtering combining marks
    result: List[str] = []
    i = 0
    while i < len(decomposed):
        char = decomposed[i]

        # Check if this is a base character
        if unicodedata.category(char) != "Mn":
            # It's a base character, check what follows
            base = char
            combining_marks: List[str] = []

            # Collect any combining marks that follow
            j = i + 1
            while j < len(decomposed) and unicodedata.category(decomposed[j]) == "Mn":
                combining_marks.append(decomposed[j])
                j += 1

            # Separate stress marks from other combining marks
            # Special handling for U+0307 (dot above):
            # - Keep it if base is 'e' or 'E' (Lithuanian e with dot)
            # - Remove it on other letters (stress mark)
            non_stress_marks: List[str] = []
            for m in combining_marks:
                if m in stress_marks:
                    # Always remove these stress marks
                    continue
                elif m == "\u0307":
                    # Dot above: keep only if base is 'e' or 'E'
                    if base.lower() == "e":
                        non_stress_marks.append(m)
                    # Otherwise skip (it's a stress mark)
                else:
                    # Keep other combining marks (Lithuanian letter components)
                    non_stress_marks.append(m)

            # Reconstruct with only non-stress marks
            reconstructed = unicodedata.normalize("NFC", base + "".join(non_stress_marks))

            # Add to result
            result.append(reconstructed)

            # Skip past the combining marks we processed
            i = j
        else:
            # Orphan combining mark - skip it if it's a stress mark, otherwise keep
            if char not in stress_marks and char != "\u0307":
                result.append(char)
            i += 1

    return "".join(result)


def clean_form(text: str) -> List[str]:
    """
    Clean a grammatical form by removing stress marks and handling alternatives.

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


def normalize_lithuanian_text(text: str) -> str:
    """
    Normalize Lithuanian text to NFC form for consistent comparison.

    Args:
        text: Text that may have various Unicode representations

    Returns:
        NFC-normalized text
    """
    return unicodedata.normalize("NFC", text)


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
