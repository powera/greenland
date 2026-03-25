"""Tests for grammatical-word lazy loading and tier/subcategory behavior."""

from __future__ import annotations

import importlib
from unittest.mock import patch

from langtools import grammatical_words
from langtools.grammatical_word_schema import build_subcategory_mapping


def _reset_language_tier_cache() -> None:
    grammatical_words._load_language_tiers.cache_clear()


def test_lazy_load_imports_only_requested_language_module() -> None:
    _reset_language_tier_cache()

    imported_module_paths: list[str] = []
    original_import_module = importlib.import_module

    def _tracking_import(module_path: str):
        if module_path.startswith("langtools.") and module_path.endswith(".grammatical_words"):
            imported_module_paths.append(module_path)
        return original_import_module(module_path)

    with patch("langtools.grammatical_words.importlib.import_module", side_effect=_tracking_import):
        assert grammatical_words.is_grammatical_word("the", "en")

    assert imported_module_paths == ["langtools.en.grammatical_words"]


def test_cache_reuses_loaded_language_data_across_repeated_calls() -> None:
    _reset_language_tier_cache()

    imported_module_paths: list[str] = []
    original_import_module = importlib.import_module

    def _tracking_import(module_path: str):
        if module_path.startswith("langtools.") and module_path.endswith(".grammatical_words"):
            imported_module_paths.append(module_path)
        return original_import_module(module_path)

    with patch("langtools.grammatical_words.importlib.import_module", side_effect=_tracking_import):
        assert grammatical_words.is_grammatical_word("the", "en")
        assert grammatical_words.is_grammatical_word("a", "en")

    assert imported_module_paths == ["langtools.en.grammatical_words"]


def test_unknown_language_fallback_for_lookup_helpers() -> None:
    _reset_language_tier_cache()

    assert grammatical_words.is_grammatical_word("the", "xx") is False
    assert grammatical_words.is_function_word("and", "xx") is False
    assert grammatical_words._get_tier_for_language("xx", "grammatical_only") is None


def test_public_registry_access_points_remain_mapping_compatible() -> None:
    _reset_language_tier_cache()

    available_languages = list(grammatical_words.GRAMMATICAL_WORDS_BY_LANGUAGE)
    assert "en" in available_languages

    english_grammatical_words = grammatical_words.GRAMMATICAL_ONLY_BY_LANGUAGE["en"]
    assert "the" in english_grammatical_words

    english_function_words = grammatical_words.FUNCTION_WORDS_BY_LANGUAGE["en"]
    assert "and" in english_function_words


def test_build_subcategory_mapping_derives_expected_tier_membership() -> None:
    personal_pronouns = frozenset({"i"})
    grammatical_words_set = frozenset({"the", "am", "n't", "eh"})
    function_words = frozenset({"in", "and"})
    non_personal_pronouns = frozenset({"this", "who", "that"})

    subcategory_mapping = build_subcategory_mapping(
        personal_pronouns=personal_pronouns,
        grammatical_words=grammatical_words_set,
        function_words=function_words,
        non_personal_pronouns=non_personal_pronouns,
        articles=frozenset({"the"}),
        auxiliaries=frozenset({"am"}),
        contractions=frozenset({"n't"}),
        prepositions=frozenset({"in"}),
        interrogatives=frozenset({"who"}),
        demonstratives=frozenset({"that"}),
    )

    assert subcategory_mapping["personal_pronouns"] == personal_pronouns
    assert subcategory_mapping["articles"] == frozenset({"the"})
    assert subcategory_mapping["auxiliaries"] == frozenset({"am"})
    assert subcategory_mapping["contractions"] == frozenset({"n't"})
    assert subcategory_mapping["particles"] == frozenset({"eh"})
    assert subcategory_mapping["prepositions"] == frozenset({"in"})
    assert subcategory_mapping["conjunctions"] == frozenset({"and"})
    assert subcategory_mapping["interrogatives"] == frozenset({"who"})
    assert subcategory_mapping["demonstratives"] == frozenset({"that"})
    assert subcategory_mapping["determiners"] == frozenset({"this"})
