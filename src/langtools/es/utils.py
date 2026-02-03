"""Spanish-specific utility functions."""

import unicodedata
from typing import List, Optional, Tuple

from langtools.es.types import SpanishGender


def normalize_spanish_text(text: str) -> str:
    """
    Normalize Spanish text to NFC form.

    Spanish uses special characters: á, é, í, ó, ú, ü, ñ, Á, É, Í, Ó, Ú, Ü, Ñ
    These should be preserved during normalization.

    Args:
        text: Text that may have various Unicode representations

    Returns:
        NFC-normalized text
    """
    return unicodedata.normalize("NFC", text)


def clean_form(text: str) -> List[str]:
    """
    Clean a Spanish grammatical form by normalizing and handling alternatives.

    Args:
        text: Raw form text (may contain slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text.strip() in ("", "-", "\u2014", "\u2013", "—"):
        return []

    # Split by slash or comma to handle alternative forms
    forms: List[str] = []
    for part in text.split("/"):
        for subpart in part.split(","):
            cleaned = subpart.strip()
            if cleaned and cleaned not in ("-", "—", "\u2014", "\u2013"):
                # Normalize to NFC
                normalized = normalize_spanish_text(cleaned)
                forms.append(normalized)

    return forms


def extract_article(text: str) -> Tuple[str, str]:
    """
    Extract the article from a Spanish noun phrase.

    Args:
        text: Text like "el perro" or "la casa"

    Returns:
        Tuple of (article, noun) or ("", text) if no article found
    """
    articles = {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "lo",  # neuter article
    }
    parts = text.split(None, 1)
    if len(parts) == 2 and parts[0].lower() in articles:
        return parts[0], parts[1]
    return "", text


def detect_gender_from_article(article: str) -> Optional[SpanishGender]:
    """
    Detect Spanish grammatical gender from article.

    Args:
        article: Spanish article (el, la, etc.)

    Returns:
        SpanishGender or None if unknown
    """
    article_lower = article.lower()
    masculine = {"el", "los", "un", "unos"}
    feminine = {"la", "las", "una", "unas"}

    if article_lower in masculine:
        return SpanishGender.MASCULINE
    elif article_lower in feminine:
        return SpanishGender.FEMININE

    return None


def detect_gender_from_word(word: str) -> Optional[SpanishGender]:
    """
    Attempt to detect Spanish grammatical gender from word ending.

    This is a heuristic that works for most regular nouns but has exceptions.

    Args:
        word: Spanish word

    Returns:
        SpanishGender or None if uncertain
    """
    word_lower = word.lower()

    # Common masculine endings
    if word_lower.endswith(("o", "or", "aje", "an")):
        return SpanishGender.MASCULINE

    # Common feminine endings
    if word_lower.endswith(("a", "ión", "dad", "tad", "tud", "umbre", "ie", "ez")):
        return SpanishGender.FEMININE

    return None
