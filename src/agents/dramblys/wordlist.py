"""
Wordlist file parsing and database coverage checking.

Parses wikitext-format word list files (like Ogden's Basic English)
and checks coverage against the linguistics database.
"""

import re
from typing import Any, Dict, List, Set

from wordfreq.storage.models.schema import DerivativeForm, Lemma


def parse_wikitext_file(file_path: str) -> List[str]:
    """
    Parse a wikitext file and extract words from wiki-style links.

    Handles patterns like:
      [[wikt:word|word]]
      [[wikt:word#Anchor|word]]
      [[word]]
      [[page|display]]
      [[:wikt:word|word]]

    Skips section headers (=== A ===), category labels ('''Basic:'''),
    and parenthetical notes like (less, least).

    Args:
        file_path: Path to the wikitext file

    Returns:
        Deduplicated list of words (preserving first-seen order)
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match all wikitext link patterns
    # [[wikt:word#Anchor|display]], [[wikt:word|display]], [[:wikt:word|display]],
    # [[page|display]], [[word]]
    link_pattern = re.compile(r"\[\[:?(?:[^|\]]*\|)?([^\]]+)\]\]")

    seen: Set[str] = set()
    words: List[str] = []

    for match in link_pattern.finditer(content):
        display_text = match.group(1).strip()

        # Skip section headers used as links (single letters like [[A]], [[B]])
        if len(display_text) == 1 and display_text.isupper():
            continue

        # Skip category/prefix markers like "centi-", "kilo-", "micro-", "milli-", "deci-"
        if display_text.endswith("-"):
            continue

        # Normalize: lowercase, strip whitespace
        word_lower = display_text.lower()

        # Skip if already seen
        if word_lower in seen:
            continue

        # Skip words with spaces (compound phrases like "good morning")
        if " " in word_lower:
            continue

        seen.add(word_lower)
        words.append(word_lower)

    return words


def get_grammatical_stopwords() -> Set[str]:
    """
    Return grammatical stopwords that should be filtered from wordlist checks.

    Includes only true grammatical/function words: pronouns, auxiliary verbs,
    prepositions, conjunctions, determiners, and contractions.

    Explicitly does NOT include COMMON_VERBS, COMMON_NOUNS, COMMON_ADVERBS,
    or MISC_WORDS, as those contain real content words that belong in the database.

    Returns:
        Set of lowercased grammatical stopwords
    """
    from util.stopwords import CONTRACTIONS, all_stopwords

    result: Set[str] = set()
    for word in all_stopwords:
        result.add(word.lower())
    for word in CONTRACTIONS:
        result.add(word.lower())
    return result


def get_existing_english_words(session: Any) -> Set[str]:
    """
    Get all English words currently in the database (lemmas + derivative forms).

    Args:
        session: SQLAlchemy database session

    Returns:
        Set of lowercased English words found in the database
    """
    existing_words: Set[str] = set()

    # Get all lemma texts, including the base word without disambiguation suffix.
    # E.g. "light (color)" adds both "light (color)" and "light".
    lemmas = session.query(Lemma).all()
    for lemma in lemmas:
        lemma_lower = lemma.lemma_text.lower()
        existing_words.add(lemma_lower)
        paren_idx = lemma_lower.find(" (")
        if paren_idx > 0:
            existing_words.add(lemma_lower[:paren_idx])

    # Get all English derivative forms
    english_forms = session.query(DerivativeForm).filter(DerivativeForm.language_code == "en").all()
    for form in english_forms:
        existing_words.add(form.derivative_form_text.lower())

    return existing_words


def check_wordlist_coverage(file_path: str, session: Any) -> Dict[str, Any]:
    """
    Check how many words from a wordlist file are covered by the database.

    Args:
        file_path: Path to the wikitext word list file
        session: SQLAlchemy database session

    Returns:
        Dictionary with coverage statistics and list of missing words
    """
    parsed_words = parse_wikitext_file(file_path)
    existing_words = get_existing_english_words(session)
    grammatical_stops = get_grammatical_stopwords()

    in_database: List[str] = []
    filtered_stopwords: List[str] = []
    missing_words: List[str] = []

    for word in parsed_words:
        if word in existing_words:
            in_database.append(word)
        elif word in grammatical_stops:
            filtered_stopwords.append(word)
        else:
            missing_words.append(word)

    missing_words.sort()

    return {
        "file_path": file_path,
        "total_words": len(parsed_words),
        "in_database": len(in_database),
        "grammatical_stopwords_filtered": len(filtered_stopwords),
        "missing_count": len(missing_words),
        "missing_words": missing_words,
    }
