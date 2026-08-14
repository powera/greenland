"""Compatibility exports for :mod:`reports.wordlist_coverage`."""

from reports.wordlist_coverage import (
    check_wordlist_coverage,
    get_existing_english_words,
    get_grammatical_stopwords,
    parse_wikitext_file,
)

__all__ = [
    "check_wordlist_coverage",
    "get_existing_english_words",
    "get_grammatical_stopwords",
    "parse_wikitext_file",
]
