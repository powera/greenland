"""German-specific utility functions."""

import unicodedata
from typing import List


def normalize_german_text(text: str) -> str:
    """
    Normalize German text to NFC form.

    German uses special characters: ä, ö, ü, Ä, Ö, Ü, ß
    These should be preserved during normalization.

    Args:
        text: Text that may have various Unicode representations

    Returns:
        NFC-normalized text
    """
    return unicodedata.normalize("NFC", text)


def clean_form(text: str) -> List[str]:
    """
    Clean a German grammatical form by normalizing and handling alternatives.

    Args:
        text: Raw form text (may contain slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013", "—"):
        return []

    # Split by slash or comma to handle alternative forms
    # German Wiktionary sometimes uses comma for alternatives
    forms: List[str] = []
    for part in text.split("/"):
        for subpart in part.split(","):
            cleaned = subpart.strip()
            if cleaned and cleaned not in ("-", "—", "\u2014", "\u2013"):
                # Normalize to NFC
                normalized = normalize_german_text(cleaned)
                forms.append(normalized)

    return forms


def extract_article(text: str) -> tuple[str, str]:
    """
    Extract the article from a German noun phrase.

    Args:
        text: Text like "der Hund" or "die Katze"

    Returns:
        Tuple of (article, noun) or ("", text) if no article found
    """
    articles = {
        "der",
        "die",
        "das",
        "dem",
        "den",
        "des",
        "ein",
        "eine",
        "einem",
        "einen",
        "einer",
        "eines",
    }
    parts = text.split(None, 1)
    if len(parts) == 2 and parts[0].lower() in articles:
        return parts[0], parts[1]
    return "", text


def detect_gender_from_article(article: str) -> str:
    """
    Detect German grammatical gender from article.

    Args:
        article: German article (der, die, das, etc.)

    Returns:
        Gender code: 'm', 'f', 'n', or '' if unknown
    """
    article_lower = article.lower()
    masculine = {"der", "den", "dem", "des", "ein", "einen", "einem", "eines"}
    feminine = {"die", "der", "eine", "einer"}
    neuter = {"das", "dem", "des", "ein", "einem", "eines"}

    # Note: some articles are ambiguous (der can be masc nom or fem gen/dat)
    # This is a simplified detection
    if article_lower in ("der",):
        return "m"  # Most common use
    elif article_lower in ("die",):
        return "f"  # Most common use (also plural)
    elif article_lower in ("das",):
        return "n"
    elif article_lower in ("ein", "einen"):
        return "m"  # Or neuter for 'ein'
    elif article_lower in ("eine", "einer"):
        return "f"

    return ""

def strip_subject_pronoun(text: str) -> str:
    """Strip a German subject pronoun from the beginning of a verb phrase."""
    normalized = normalize_german_text(text.strip().lower())
    if not normalized:
        return ""

    combined_pronouns = ["er/sie ", "sie/er ", "er / sie ", "sie / er "]
    for pronoun in combined_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()

    pronouns = ["ich ", "du ", "er ", "sie ", "es ", "wir ", "ihr "]
    for pronoun in pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()
    return normalized

