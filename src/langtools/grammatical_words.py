"""Cross-language grammatical-word registry.

Each language provides two tiers:

* **grammatical_only** – pure grammar (articles, pronouns, auxiliaries,
  particles).  The sentence linker should skip these; they are never lemmas.
* **also_lemma** – function words that *also* appear as teachable lemma
  entries in data/release (conjunctions, prepositions, interrogatives,
  determiners).  The linker should try to resolve these to lemmas.

``is_grammatical_word`` checks the narrow *grammatical_only* set — the one
the linker cares about.  ``is_function_word`` checks the broad union.
"""

from typing import Final

from langtools.de.grammatical_words import (
    GERMAN_ALSO_LEMMA,
    GERMAN_GRAMMATICAL_ONLY,
    GERMAN_GRAMMATICAL_WORDS,
)
from langtools.en.grammatical_words import (
    ENGLISH_ALSO_LEMMA,
    ENGLISH_GRAMMATICAL_ONLY_WITH_CONTRACTIONS,
    ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS,
)
from langtools.es.grammatical_words import (
    SPANISH_ALSO_LEMMA,
    SPANISH_GRAMMATICAL_ONLY,
    SPANISH_GRAMMATICAL_WORDS,
)
from langtools.fr.grammatical_words import (
    FRENCH_ALSO_LEMMA,
    FRENCH_GRAMMATICAL_ONLY,
    FRENCH_GRAMMATICAL_WORDS,
)
from langtools.lt.grammatical_words import (
    LITHUANIAN_ALSO_LEMMA,
    LITHUANIAN_GRAMMATICAL_ONLY,
    LITHUANIAN_GRAMMATICAL_WORDS,
)
from langtools.zh.grammatical_words import (
    CHINESE_ALSO_LEMMA,
    CHINESE_GRAMMATICAL_ONLY,
    CHINESE_GRAMMATICAL_WORDS,
)

# Narrow set: pure grammar — the linker skips these.
GRAMMATICAL_ONLY_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_GRAMMATICAL_ONLY,
    "en": ENGLISH_GRAMMATICAL_ONLY_WITH_CONTRACTIONS,
    "es": SPANISH_GRAMMATICAL_ONLY,
    "fr": FRENCH_GRAMMATICAL_ONLY,
    "lt": LITHUANIAN_GRAMMATICAL_ONLY,
    "zh": CHINESE_GRAMMATICAL_ONLY,
}

# Function words that are also lemmas.
ALSO_LEMMA_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_ALSO_LEMMA,
    "en": ENGLISH_ALSO_LEMMA,
    "es": SPANISH_ALSO_LEMMA,
    "fr": FRENCH_ALSO_LEMMA,
    "lt": LITHUANIAN_ALSO_LEMMA,
    "zh": CHINESE_ALSO_LEMMA,
}

# Broad union (backward-compatible).
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
    """Return True if *word* is a pure grammatical word (never a lemma).

    This checks the narrow *grammatical_only* set.  Conjunctions,
    prepositions, interrogatives, and determiners that have data/release
    entries are **not** considered grammatical by this function.
    """
    normalized = normalize_grammatical_word(word)
    if not normalized:
        return False
    words = GRAMMATICAL_ONLY_BY_LANGUAGE.get(language_code)
    if words is None:
        return False
    return normalized in words


def is_function_word(word: str, language_code: str) -> bool:
    """Return True if *word* is any kind of function word (broad check).

    Includes both *grammatical_only* and *also_lemma* tiers.
    """
    normalized = normalize_grammatical_word(word)
    if not normalized:
        return False
    words = GRAMMATICAL_WORDS_BY_LANGUAGE.get(language_code)
    if words is None:
        return False
    return normalized in words
