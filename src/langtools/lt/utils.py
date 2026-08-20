"""Lithuanian-specific utility functions."""

import re
import unicodedata
from typing import List

from langtools.lt.letters import LETTERS_UPPER

# Lithuanian alphabet as a lowercase character-class body, derived from the
# canonical alphabet in letters.py rather than restated, so the two cannot
# drift apart:
#   a ą b c č d e ę ė f g h i į y j k l m n o p r s š t u ų ū v z ž
LITHUANIAN_CHARS = "".join(LETTERS_UPPER).lower()


def remove_stress_marks(text: str) -> str:
    """
    Remove stress/accent marks from Lithuanian text while preserving Lithuanian letters.

    Lithuanian has distinct letters with diacritics (ą, č, ė, ę, į, š, ū, ų, ž)
    that must be preserved. However, stress marks (acute, grave, tilde)
    that can appear on ANY vowel for pronunciation are removed.

    Complex case: stress marks can appear on top of Lithuanian letters (e.g., ų with tilde)
    In this case, we need to preserve the Lithuanian letter (ų) but remove the stress (tilde).

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
    #       - On 'e' or 'E': forms Lithuanian ė (must be preserved)
    #       - On other vowels: stress/accent mark (must be removed)
    # Note: U+030C (COMBINING CARON) is NOT a stress mark - it's part of č, š, ž
    # Note: U+0304 (COMBINING MACRON) is NOT a stress mark - it's part of ū
    # Note: U+0328 (COMBINING OGONEK) is NOT a stress mark - it's part of ą, ę, į, ų
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
            # - Keep it if base is 'e' or 'E' (Lithuanian ė)
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


def normalize_lithuanian_text(text: str) -> str:
    """
    Normalize Lithuanian text: remove stress marks and normalize to NFC.

    Args:
        text: Text that may have stress marks and various Unicode representations

    Returns:
        Normalized text without stress marks
    """
    return remove_stress_marks(text)


def clean_form(text: str) -> List[str]:
    """
    Clean a Lithuanian grammatical form by removing stress marks and handling alternatives.

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
    """Strip a Lithuanian subject pronoun from the beginning of a verb phrase."""
    normalized = normalize_lithuanian_text(text.strip().lower())
    if not normalized:
        return ""

    combined_pronouns = ["jis/ji ", "ji/jis ", "jis / ji ", "ji / jis "]
    for pronoun in combined_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()

    pronouns = ["aš ", "tu ", "jis ", "ji ", "mes ", "jūs ", "jie ", "jos "]
    for pronoun in pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized


def sanitize_lithuanian_word(word: str) -> str:
    """
    Sanitize a Lithuanian word or phrase for use as a filename.

    Keeps Lithuanian letters, basic Latin letters, hyphens and underscores;
    spaces become underscores so multi-word phrases stay one filename.

    Args:
        word: The Lithuanian word or phrase to sanitize

    Returns:
        Sanitized filename-safe version, or "" if nothing survives
        sanitization or the result exceeds 100 characters
    """
    word = word.strip().lower()

    # Replace spaces with underscores for multi-word phrases
    word_with_underscores = word.replace(" ", "_")

    # Allow all Lithuanian letters, basic Latin letters, and safe characters
    sanitized = re.sub(r"[^a-z" + LITHUANIAN_CHARS + r"\-_]", "", word_with_underscores)

    if not sanitized or len(sanitized) > 100:
        return ""

    return sanitized
