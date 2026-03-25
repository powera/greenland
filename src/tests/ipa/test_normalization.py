"""Tests for shared IPA normalization utilities."""

from ipa import (
    are_ipa_equivalent,
    is_ipa_levenshtein_match,
    normalize_ipa,
    weighted_similarity_ratio,
)


def test_normalize_ipa_strips_delimiters() -> None:
    assert normalize_ipa("/ˈwɔːtər/") == "ˈwɔːtər"


def test_normalize_ipa_removes_tie_bar() -> None:
    assert normalize_ipa("t͡ɕ") == "tɕ"


def test_weighted_similarity_ratio_prefers_similar_chars() -> None:
    similar_ratio = weighted_similarity_ratio("r", "ɹ")
    unrelated_ratio = weighted_similarity_ratio("r", "z")
    assert similar_ratio > unrelated_ratio


def test_are_ipa_equivalent_for_close_dialects() -> None:
    assert are_ipa_equivalent("/ˈwɔːtər/", "ˈwɔtɚ", threshold=0.6)


def test_is_ipa_levenshtein_match_alias() -> None:
    assert is_ipa_levenshtein_match("kæt", "kæt")
