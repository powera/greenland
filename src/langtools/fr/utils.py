"""French-specific utility functions."""

import unicodedata
from typing import List


def normalize_french_text(text: str) -> str:
    """
    Normalize French text to NFC form.

    French uses accented characters: à, â, ç, é, è, ê, ë, î, ï, ô, ù, û, ü, ÿ, æ, œ
    These should be preserved during normalization.

    Args:
        text: Text that may have various Unicode representations

    Returns:
        NFC-normalized text
    """
    return unicodedata.normalize("NFC", text)


def clean_form(text: str) -> List[str]:
    """
    Clean a French grammatical form by normalizing and handling alternatives.

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
                normalized = normalize_french_text(cleaned)
                forms.append(normalized)

    return forms


def extract_article(text: str) -> tuple[str, str]:
    """
    Extract the article from a French noun phrase.

    Args:
        text: Text like "le chien" or "la maison"

    Returns:
        Tuple of (article, noun) or ("", text) if no article found
    """
    articles = {
        "le",
        "la",
        "l'",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de la",
        "de l'",
        "au",
        "aux",
    }
    text_lower = text.lower()

    # Check for elided article first (l')
    if text_lower.startswith("l'"):
        return "l'", text[2:]

    # Check for compound articles
    for compound in ["de la", "de l'"]:
        if text_lower.startswith(compound + " "):
            return compound, text[len(compound) + 1 :]

    # Check for simple articles
    parts = text.split(None, 1)
    if len(parts) == 2 and parts[0].lower() in articles:
        return parts[0], parts[1]

    return "", text


def detect_gender_from_article(article: str) -> str:
    """
    Detect French grammatical gender from article.

    Args:
        article: French article (le, la, un, une, etc.)

    Returns:
        Gender code: 'm', 'f', or '' if unknown
    """
    article_lower = article.lower().strip()

    masculine = {"le", "un", "du", "au"}
    feminine = {"la", "une", "de la"}

    if article_lower in masculine:
        return "m"
    elif article_lower in feminine:
        return "f"
    elif article_lower in ("l'", "de l'"):
        # Elided articles are ambiguous
        return ""
    elif article_lower in ("les", "des", "aux"):
        # Plural articles don't indicate gender
        return ""

    return ""


def strip_subject_pronoun(text: str) -> str:
    """Strip a French subject pronoun from the beginning of a conjugated verb form.

    Handles simple pronouns (je, tu, il, elle, on, nous, vous, ils, elles),
    combined forms (ils/elles, il/elle/on, il/elle), and the elided j' form.

    Args:
        text: A French conjugated verb form, possibly prefixed with a subject pronoun.

    Returns:
        The bare verb form, stripped and lowercased.
    """
    normalized = text.strip().lower()
    if not normalized:
        return ""

    # Handle elided j' first (e.g. "j'ouvre" -> "ouvre", "j'ai ouvert" -> "ai ouvert")
    if normalized.startswith("j'") or normalized.startswith("j\u2019"):
        return normalized[2:].strip()

    # Combined pronoun forms (must check before simple pronouns)
    combined_pronouns = ["ils/elles ", "il/elle/on ", "il/elle "]
    for pronoun in combined_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()

    # Simple subject pronouns
    simple_pronouns = [
        "elles ",
        "elle ",
        "nous ",
        "vous ",
        "ils ",
        "il ",
        "je ",
        "tu ",
        "on ",
    ]
    for pronoun in simple_pronouns:
        if normalized.startswith(pronoun):
            return normalized[len(pronoun) :].strip()

    # TODO: Does not strip reflexive pronouns (me/te/se/nous/vous) from
    # subject+reflexive combinations like "je me lève" or "il s'assoit".
    return normalized


def is_elided_form(word: str) -> bool:
    """
    Check if a word would cause elision (starts with vowel or silent h).

    Args:
        word: French word to check

    Returns:
        True if the word would cause elision
    """
    if not word:
        return False

    vowels = "aeiouyàâäéèêëïîôùûüÿæœ"
    first_char = word[0].lower()

    # Words starting with vowels cause elision
    if first_char in vowels:
        return True

    # Words starting with silent h also cause elision
    # This is a simplification; in practice, you'd need a dictionary
    # Common words with silent h: homme, heure, histoire, hôtel, hiver, etc.
    silent_h_words = {
        "homme",
        "heure",
        "histoire",
        "hôtel",
        "hiver",
        "habitude",
        "honneur",
        "hôpital",
        "huile",
        "humeur",
        "humain",
    }

    if first_char == "h" and word.lower() in silent_h_words:
        return True

    return False
