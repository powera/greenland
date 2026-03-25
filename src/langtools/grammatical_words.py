"""Cross-language grammatical-word registry.

Each language provides four tiers:

1. **personal_pronouns** – I/me/my, ich/du/er, 我/你/他, …
2. **grammatical_words** – articles, auxiliaries, particles, contractions
3. **function_words** – conjunctions, prepositions (in data/release)
4. **non_personal_pronouns** – who/this/that, wer/dieser, 谁/这/那 (in data/release)

Tiers 1–2 have no analogues in data/release (linker skips them).
Tiers 3–4 do (linker should resolve them to lemmas).

``is_grammatical_word`` checks tiers 1+2 (the narrow set).
``is_function_word`` checks all four tiers (the broad set).
"""

from typing import Final

from langtools.de.grammatical_words import (
    GERMAN_ALL_TIERS,
    GERMAN_ALSO_LEMMA,
    GERMAN_FUNCTION_WORDS,
    GERMAN_GRAMMATICAL_ONLY,
    GERMAN_NON_PERSONAL_PRONOUNS,
    GERMAN_PERSONAL_PRONOUNS,
)
from langtools.en.grammatical_words import (
    ENGLISH_ALL_TIERS,
    ENGLISH_ALSO_LEMMA,
    ENGLISH_FUNCTION_WORDS,
    ENGLISH_GRAMMATICAL_ONLY,
    ENGLISH_NON_PERSONAL_PRONOUNS,
    ENGLISH_PERSONAL_PRONOUNS,
)
from langtools.es.grammatical_words import (
    SPANISH_ALL_TIERS,
    SPANISH_ALSO_LEMMA,
    SPANISH_FUNCTION_WORDS,
    SPANISH_GRAMMATICAL_ONLY,
    SPANISH_NON_PERSONAL_PRONOUNS,
    SPANISH_PERSONAL_PRONOUNS,
)
from langtools.fr.grammatical_words import (
    FRENCH_ALL_TIERS,
    FRENCH_ALSO_LEMMA,
    FRENCH_FUNCTION_WORDS,
    FRENCH_GRAMMATICAL_ONLY,
    FRENCH_NON_PERSONAL_PRONOUNS,
    FRENCH_PERSONAL_PRONOUNS,
)
from langtools.lt.grammatical_words import (
    LITHUANIAN_ALL_TIERS,
    LITHUANIAN_ALSO_LEMMA,
    LITHUANIAN_FUNCTION_WORDS,
    LITHUANIAN_GRAMMATICAL_ONLY,
    LITHUANIAN_NON_PERSONAL_PRONOUNS,
    LITHUANIAN_PERSONAL_PRONOUNS,
)
from langtools.zh.grammatical_words import (
    CHINESE_ALL_TIERS,
    CHINESE_ALSO_LEMMA,
    CHINESE_FUNCTION_WORDS,
    CHINESE_GRAMMATICAL_ONLY,
    CHINESE_NON_PERSONAL_PRONOUNS,
    CHINESE_PERSONAL_PRONOUNS,
)

# ── per-tier dicts ─────────────────────────────────────────────────────

PERSONAL_PRONOUNS_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_PERSONAL_PRONOUNS,
    "en": ENGLISH_PERSONAL_PRONOUNS,
    "es": SPANISH_PERSONAL_PRONOUNS,
    "fr": FRENCH_PERSONAL_PRONOUNS,
    "lt": LITHUANIAN_PERSONAL_PRONOUNS,
    "zh": CHINESE_PERSONAL_PRONOUNS,
}

NON_PERSONAL_PRONOUNS_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_NON_PERSONAL_PRONOUNS,
    "en": ENGLISH_NON_PERSONAL_PRONOUNS,
    "es": SPANISH_NON_PERSONAL_PRONOUNS,
    "fr": FRENCH_NON_PERSONAL_PRONOUNS,
    "lt": LITHUANIAN_NON_PERSONAL_PRONOUNS,
    "zh": CHINESE_NON_PERSONAL_PRONOUNS,
}

FUNCTION_WORDS_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_FUNCTION_WORDS,
    "en": ENGLISH_FUNCTION_WORDS,
    "es": SPANISH_FUNCTION_WORDS,
    "fr": FRENCH_FUNCTION_WORDS,
    "lt": LITHUANIAN_FUNCTION_WORDS,
    "zh": CHINESE_FUNCTION_WORDS,
}

# ── aggregate dicts ────────────────────────────────────────────────────

# Tiers 1+2: linker skips these (not in data/release).
GRAMMATICAL_ONLY_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_GRAMMATICAL_ONLY,
    "en": ENGLISH_GRAMMATICAL_ONLY,
    "es": SPANISH_GRAMMATICAL_ONLY,
    "fr": FRENCH_GRAMMATICAL_ONLY,
    "lt": LITHUANIAN_GRAMMATICAL_ONLY,
    "zh": CHINESE_GRAMMATICAL_ONLY,
}

# Tiers 3+4: linker should resolve these to lemmas.
ALSO_LEMMA_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_ALSO_LEMMA,
    "en": ENGLISH_ALSO_LEMMA,
    "es": SPANISH_ALSO_LEMMA,
    "fr": FRENCH_ALSO_LEMMA,
    "lt": LITHUANIAN_ALSO_LEMMA,
    "zh": CHINESE_ALSO_LEMMA,
}

# All four tiers (broadest).
GRAMMATICAL_WORDS_BY_LANGUAGE: Final[dict[str, frozenset[str]]] = {
    "de": GERMAN_ALL_TIERS,
    "en": ENGLISH_ALL_TIERS,
    "es": SPANISH_ALL_TIERS,
    "fr": FRENCH_ALL_TIERS,
    "lt": LITHUANIAN_ALL_TIERS,
    "zh": CHINESE_ALL_TIERS,
}


def normalize_grammatical_word(word: str) -> str:
    """Normalize a token before grammatical-word lookup."""
    return word.strip().lower()


def is_grammatical_word(word: str, language_code: str) -> bool:
    """Return True if *word* is a pure grammatical word (never a lemma).

    Checks tiers 1+2 (personal pronouns + grammatical words).
    Conjunctions, prepositions, interrogatives, and determiners that have
    data/release entries are **not** considered grammatical by this function.
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

    Checks all four tiers.
    """
    normalized = normalize_grammatical_word(word)
    if not normalized:
        return False
    words = GRAMMATICAL_WORDS_BY_LANGUAGE.get(language_code)
    if words is None:
        return False
    return normalized in words
