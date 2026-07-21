"""Cross-language Wiktionary form dispatcher.

Mirrors :mod:`langtools.tokenizer` and :mod:`langtools.verb_forms`: each
language that can parse forms from Wiktionary provides a
``langtools.<code>.wiktionary`` module with a parser class exposing the
standard ``get_noun_declensions`` / ``get_verb_conjugations`` /
``get_adjective_declensions`` / ``get_adverb_forms`` methods, each returning a
``(result, success)`` tuple whose ``result.forms`` is a ``Dict[str, str]``.

This replaces the per-language ``if/elif`` ladder that previously lived in
``wordfreq.translation.wiktionary_forms``: callers now reach the parsers
through this single dispatcher instead of a wordfreq-side wrapper.

Parsing genuinely fetches Wiktionary, so - unlike the mechanical
:mod:`langtools.inflection` / :mod:`langtools.conjugation` dispatchers - the
forms here are not derived from lexical grammar facts and this dispatcher takes
no grammar-fact arguments.
"""

import logging
from functools import lru_cache
from importlib import import_module
from typing import Callable, Dict, List, Optional, Protocol, Tuple, cast

logger = logging.getLogger(__name__)


class _FormResult(Protocol):
    """The shape shared by every parser result: a ``forms`` mapping."""

    forms: Dict[str, str]


_ParserMethod = Callable[[str], Tuple[_FormResult, bool]]

# Languages with a dedicated Wiktionary parser, mapped to (module, class name).
# The class names do not follow a mechanical convention (EnglishParser, not
# EnParser), so they are listed explicitly.
_PARSER_SPECS: Dict[str, Tuple[str, str]] = {
    "en": ("langtools.en.wiktionary", "EnglishParser"),
    "es": ("langtools.es.wiktionary", "SpanishParser"),
    "fr": ("langtools.fr.wiktionary", "FrenchParser"),
    "lt": ("langtools.lt.wiktionary", "LithuanianParser"),
}

# Part-of-speech to parser method name.
_POS_TO_METHOD: Dict[str, str] = {
    "noun": "get_noun_declensions",
    "verb": "get_verb_conjugations",
    "adjective": "get_adjective_declensions",
    "adverb": "get_adverb_forms",
}

# ---------------------------------------------------------------------------
# Mapping from Wiktionary form names to the form names expected by LLM/storage
# tasks.  Keeps Wiktionary output flowing through the same storage logic as the
# LLM path.  An empty mapping marks a language/POS whose parser output is not
# yet wired up (e.g. complex verb conjugation) and is treated as unsupported.
# ---------------------------------------------------------------------------

# English verb: Wiktionary returns 5 canonical forms.  Keys that already match
# the form_mapping pass through; "past" is remapped to the person-independent
# "3s_past" slot (English simple past is invariant across persons).
ENGLISH_VERB_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "infinitive": "infinitive",
    "3s_present": "3s_present",
    "past": "3s_past",  # English simple past is the same for all persons
    "past_participle": "past_participle",
    "present_participle": "present_participle",
}

ENGLISH_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular": "singular",
    "plural": "plural",
}

ENGLISH_ADJ_ADV_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "positive": "positive",
    "comparative": "comparative",
    "superlative": "superlative",
}

SPANISH_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular": "singular",
    "plural": "plural",
}

SPANISH_ADJ_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular_m": "singular_m",
    "singular_f": "singular_f",
    "plural_m": "plural_m",
    "plural_f": "plural_f",
}

SPANISH_ADVERB_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "positive": "positive",
    "comparative": "comparative",
    "superlative": "superlative",
}

FRENCH_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "singular": "singular",
    "plural": "plural",
}

LITHUANIAN_NOUN_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "nominative_singular": "nominative_singular",
    "nominative_plural": "nominative_plural",
    "genitive_singular": "genitive_singular",
    "genitive_plural": "genitive_plural",
    "dative_singular": "dative_singular",
    "dative_plural": "dative_plural",
    "accusative_singular": "accusative_singular",
    "accusative_plural": "accusative_plural",
    "instrumental_singular": "instrumental_singular",
    "instrumental_plural": "instrumental_plural",
    "locative_singular": "locative_singular",
    "locative_plural": "locative_plural",
    "vocative_singular": "vocative_singular",
    "vocative_plural": "vocative_plural",
}

LITHUANIAN_ADJ_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "nominative_singular_m": "nominative_singular_m",
    "nominative_singular_f": "nominative_singular_f",
    "nominative_plural_m": "nominative_plural_m",
    "nominative_plural_f": "nominative_plural_f",
}

LITHUANIAN_ADVERB_WIKTIONARY_TO_TASK: Dict[str, str] = {
    "positive": "positive",
    "comparative": "comparative",
    "superlative": "superlative",
}

# Registry of Wiktionary-to-task mappings.
WIKTIONARY_TO_TASK_MAPPINGS: Dict[str, Dict[str, Dict[str, str]]] = {
    "en": {
        "noun": ENGLISH_NOUN_WIKTIONARY_TO_TASK,
        "verb": ENGLISH_VERB_WIKTIONARY_TO_TASK,
        "adjective": ENGLISH_ADJ_ADV_WIKTIONARY_TO_TASK,
        "adverb": ENGLISH_ADJ_ADV_WIKTIONARY_TO_TASK,
    },
    "es": {
        "noun": SPANISH_NOUN_WIKTIONARY_TO_TASK,
        "verb": {},  # Spanish verb conjugation is complex, not yet mapped
        "adjective": SPANISH_ADJ_WIKTIONARY_TO_TASK,
        "adverb": SPANISH_ADVERB_WIKTIONARY_TO_TASK,
    },
    "fr": {
        "noun": FRENCH_NOUN_WIKTIONARY_TO_TASK,
        "verb": {},  # French verb conjugation is complex, not yet mapped
    },
    "lt": {
        "noun": LITHUANIAN_NOUN_WIKTIONARY_TO_TASK,
        "verb": {},  # Lithuanian verb conjugation is complex, not yet mapped
        "adjective": LITHUANIAN_ADJ_WIKTIONARY_TO_TASK,
        "adverb": LITHUANIAN_ADVERB_WIKTIONARY_TO_TASK,
    },
}


@lru_cache(maxsize=None)
def _load_parser_method(language_code: str, pos_type: str) -> Optional[_ParserMethod]:
    """Return the bound parser method for a language/POS, or None if unavailable."""
    spec = _PARSER_SPECS.get(language_code)
    method_name = _POS_TO_METHOD.get(pos_type)
    if spec is None or method_name is None:
        return None
    module_path, class_name = spec
    try:
        module = import_module(module_path)
    except ImportError:
        logger.warning("Wiktionary parser module %s not available", module_path)
        return None
    parser_cls = getattr(module, class_name, None)
    if parser_cls is None:
        logger.warning("Module %s has no class %s", module_path, class_name)
        return None
    method = getattr(parser_cls(), method_name, None)
    if not callable(method):
        return None
    return cast(_ParserMethod, method)


def get_wiktionary_forms(
    word: str, language_code: str, pos_type: str
) -> Tuple[Dict[str, str], bool]:
    """Get forms for *word* from Wiktionary.

    Args:
        word: The word to look up.
        language_code: Language code (en, es, fr, lt).
        pos_type: Part of speech (noun, verb, adjective, adverb).

    Returns:
        Tuple of (forms dict, success flag).  ``({}, False)`` when the language
        or part of speech is unsupported or parsing fails.
    """
    normalized_code = (language_code or "").strip().lower()
    normalized_pos = (pos_type or "").strip().lower()

    method = _load_parser_method(normalized_code, normalized_pos)
    if method is None:
        logger.warning("Wiktionary parsing not supported for %s %s", language_code, pos_type)
        return {}, False

    try:
        result, success = method(word)
        return result.forms, success
    except Exception as exc:  # noqa: BLE001 - parser/network errors must not propagate
        logger.error("Error fetching Wiktionary forms for '%s' (%s): %s", word, language_code, exc)
        return {}, False


def is_wiktionary_supported(language_code: str, pos_type: str) -> bool:
    """Whether Wiktionary-based generation is wired up for a language/POS pair."""
    mapping = WIKTIONARY_TO_TASK_MAPPINGS.get(language_code, {}).get(pos_type, {})
    # An empty mapping means the parser output is not yet wired to task keys.
    return bool(mapping)


def get_supported_wiktionary_tasks() -> Dict[str, List[str]]:
    """Return a mapping of language code to the POS types it supports."""
    result: Dict[str, List[str]] = {}
    for language_code, pos_types in WIKTIONARY_TO_TASK_MAPPINGS.items():
        supported_pos = [pos for pos, mapping in pos_types.items() if mapping]
        if supported_pos:
            result[language_code] = supported_pos
    return result
