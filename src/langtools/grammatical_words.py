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

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
import importlib
from typing import Final, Literal, cast


@dataclass(frozen=True)
class _LanguageTierData:
    personal_pronouns: frozenset[str]
    grammatical_only: frozenset[str]
    function_words: frozenset[str]
    non_personal_pronouns: frozenset[str]
    also_lemma: frozenset[str]
    all_tiers: frozenset[str]


_LANGUAGE_MODULE_PATHS: Final[dict[str, str]] = {
    "de": "langtools.de.grammatical_words",
    "en": "langtools.en.grammatical_words",
    "es": "langtools.es.grammatical_words",
    "fr": "langtools.fr.grammatical_words",
    "it": "langtools.it.grammatical_words",
    "ja": "langtools.ja.grammatical_words",
    "lt": "langtools.lt.grammatical_words",
    "nl": "langtools.nl.grammatical_words",
    "pt": "langtools.pt.grammatical_words",
    "sv": "langtools.sv.grammatical_words",
    "zh": "langtools.zh.grammatical_words",
}

_LANGUAGE_CONSTANT_PREFIXES: Final[dict[str, str]] = {
    "de": "GERMAN",
    "en": "ENGLISH",
    "es": "SPANISH",
    "fr": "FRENCH",
    "it": "ITALIAN",
    "ja": "JAPANESE",
    "lt": "LITHUANIAN",
    "nl": "DUTCH",
    "pt": "PORTUGUESE",
    "sv": "SWEDISH",
    "zh": "CHINESE",
}


@lru_cache(maxsize=None)
def _load_language_tiers(language_code: str) -> _LanguageTierData:
    module_path = _LANGUAGE_MODULE_PATHS.get(language_code)
    constant_prefix = _LANGUAGE_CONSTANT_PREFIXES.get(language_code)
    if module_path is None or constant_prefix is None:
        raise KeyError(language_code)

    language_module = importlib.import_module(module_path)

    def _read_tier(suffix: str) -> frozenset[str]:
        value = getattr(language_module, f"{constant_prefix}_{suffix}")
        if not isinstance(value, frozenset):
            return frozenset(value)
        return value

    return _LanguageTierData(
        personal_pronouns=_read_tier("PERSONAL_PRONOUNS"),
        grammatical_only=_read_tier("GRAMMATICAL_ONLY"),
        function_words=_read_tier("FUNCTION_WORDS"),
        non_personal_pronouns=_read_tier("NON_PERSONAL_PRONOUNS"),
        also_lemma=_read_tier("ALSO_LEMMA"),
        all_tiers=_read_tier("ALL_TIERS"),
    )


_TierName = Literal[
    "personal_pronouns",
    "grammatical_only",
    "function_words",
    "non_personal_pronouns",
    "also_lemma",
    "all_tiers",
]


def _get_tier_for_language(language_code: str, tier_name: _TierName) -> frozenset[str] | None:
    try:
        language_data = _load_language_tiers(language_code)
    except KeyError:
        return None
    return cast(frozenset[str], getattr(language_data, tier_name))


class _LanguageTierMapping(Mapping[str, frozenset[str]]):
    def __init__(self, tier_name: _TierName) -> None:
        self._tier_name = tier_name

    def __getitem__(self, language_code: str) -> frozenset[str]:
        tier = _get_tier_for_language(language_code, self._tier_name)
        if tier is None:
            raise KeyError(language_code)
        return tier

    def __iter__(self) -> Iterator[str]:
        return iter(_LANGUAGE_MODULE_PATHS)

    def __len__(self) -> int:
        return len(_LANGUAGE_MODULE_PATHS)


# ── per-tier dict-like registries ──────────────────────────────────────

PERSONAL_PRONOUNS_BY_LANGUAGE: Final[Mapping[str, frozenset[str]]] = _LanguageTierMapping(
    "personal_pronouns"
)

NON_PERSONAL_PRONOUNS_BY_LANGUAGE: Final[Mapping[str, frozenset[str]]] = _LanguageTierMapping(
    "non_personal_pronouns"
)

FUNCTION_WORDS_BY_LANGUAGE: Final[Mapping[str, frozenset[str]]] = _LanguageTierMapping(
    "function_words"
)

# ── aggregate dict-like registries ─────────────────────────────────────

# Tiers 1+2: linker skips these (not in data/release).
GRAMMATICAL_ONLY_BY_LANGUAGE: Final[Mapping[str, frozenset[str]]] = _LanguageTierMapping(
    "grammatical_only"
)

# Tiers 3+4: linker should resolve these to lemmas.
ALSO_LEMMA_BY_LANGUAGE: Final[Mapping[str, frozenset[str]]] = _LanguageTierMapping("also_lemma")

# All four tiers (broadest).
GRAMMATICAL_WORDS_BY_LANGUAGE: Final[Mapping[str, frozenset[str]]] = _LanguageTierMapping(
    "all_tiers"
)


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

    grammatical_only = _get_tier_for_language(language_code, "grammatical_only")
    if grammatical_only is None:
        return False
    return normalized in grammatical_only


def is_function_word(word: str, language_code: str) -> bool:
    """Return True if *word* is any kind of function word (broad check).

    Checks all four tiers.
    """
    normalized = normalize_grammatical_word(word)
    if not normalized:
        return False

    all_tiers = _get_tier_for_language(language_code, "all_tiers")
    if all_tiers is None:
        return False
    return normalized in all_tiers
