"""Tests for the English possessive rule in langtools.en.inflection."""

from typing import Dict, Optional

import pytest

from langtools.en.inflection import build_possessive_forms


@pytest.mark.parametrize(
    "singular, plural, expected",
    [
        ("world", "worlds", {"possessive_singular": "world's", "possessive_plural": "worlds'"}),
        ("boss", "bosses", {"possessive_singular": "boss's", "possessive_plural": "bosses'"}),
        (
            "child",
            "children",
            {"possessive_singular": "child's", "possessive_plural": "children's"},
        ),
        ("woman", "women", {"possessive_singular": "woman's", "possessive_plural": "women's"}),
        ("poverty", None, {"possessive_singular": "poverty's"}),
        ("Shanghai", None, {"possessive_singular": "Shanghai's"}),
        ("James", None, {"possessive_singular": "James's"}),
        (
            "mother-in-law",
            "mothers-in-law",
            {
                "possessive_singular": "mother-in-law's",
                "possessive_plural": "mothers-in-law's",
            },
        ),
        (
            "ice cream",
            "ice creams",
            {"possessive_singular": "ice cream's", "possessive_plural": "ice creams'"},
        ),
    ],
)
def test_possessive_forms(singular: str, plural: Optional[str], expected: Dict[str, str]) -> None:
    assert build_possessive_forms(singular, plural) == expected


def test_plurale_tantum_has_only_the_plural_possessive() -> None:
    assert build_possessive_forms("scissors", "scissors", plurale_tantum=True) == {
        "possessive_plural": "scissors'"
    }


def test_invariant_noun_ending_in_s_has_only_the_plural_possessive() -> None:
    """ "species" is one spelling for both numbers, so "species's" is never built."""
    assert build_possessive_forms("species", "species") == {"possessive_plural": "species'"}


def test_invariant_noun_not_ending_in_s_keeps_both() -> None:
    assert build_possessive_forms("sheep", "sheep") == {
        "possessive_singular": "sheep's",
        "possessive_plural": "sheep's",
    }


@pytest.mark.parametrize("noun", ["Mr.", "head (of cattle)", "rock 'n'", "1990s", ""])
def test_unpossessable_text_is_declined(noun: str) -> None:
    assert build_possessive_forms(noun) is None
