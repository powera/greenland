"""Cross-language grammatical-word registry."""

from typing import Final

from langtools.de.grammatical_words import GERMAN_GRAMMATICAL_WORDS
from langtools.en.grammatical_words import ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS
from langtools.es.grammatical_words import SPANISH_GRAMMATICAL_WORDS
from langtools.fr.grammatical_words import FRENCH_GRAMMATICAL_WORDS
from langtools.lt.grammatical_words import LITHUANIAN_GRAMMATICAL_WORDS
from langtools.zh.grammatical_words import CHINESE_GRAMMATICAL_WORDS

GRAMMATICAL_WORDS_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_GRAMMATICAL_WORDS,
    "en": ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS,
    "es": SPANISH_GRAMMATICAL_WORDS,
    "fr": FRENCH_GRAMMATICAL_WORDS,
    "lt": LITHUANIAN_GRAMMATICAL_WORDS,
    "zh": CHINESE_GRAMMATICAL_WORDS,
}


def normalize_grammatical_word(word: str) -> str:
    """Normalize a token before grammatical-word lookup."""
    return word.strip().lower()


def is_grammatical_word(word: str, language_code: str) -> bool:
    """Return whether *word* is configured as a grammatical word."""
    normalized_word = normalize_grammatical_word(word)
    if not normalized_word:
        return False
    language_words = GRAMMATICAL_WORDS_BY_LANGUAGE.get(language_code)
    if language_words is None:
        return False
    return normalized_word in language_words
