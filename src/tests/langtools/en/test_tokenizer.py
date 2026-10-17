"""Tests for the English contraction hook in langtools.en.tokenizer."""

from typing import List

import pytest

from langtools.tokenizer import lemma_lookup_keys, split_contractions


@pytest.mark.parametrize(
    "token, expected",
    [
        ("I'm", ["i", "am"]),
        ("don't", ["do", "not"]),
        ("can't", ["can", "not"]),
        ("won't", ["will", "not"]),
        ("let's", ["let", "us"]),
        ("they're", ["they", "are"]),
        ("It’s", ["it", "is"]),
        # Not listed: the regular clitic rules apply.
        ("should've", ["should", "have"]),
        ("Mary'll", ["mary", "will"]),
        ("mightn't", ["might", "not"]),
    ],
)
def test_contractions_split_into_words(token: str, expected: List[str]) -> None:
    assert split_contractions("en", token) == expected


@pytest.mark.parametrize("token", ["world's", "children's", "o'clock", "ma'am", "house"])
def test_non_contractions_are_left_whole(token: str) -> None:
    assert split_contractions("en", token) == [token]


def test_lookup_keys_include_contraction_parts() -> None:
    assert lemma_lookup_keys("en", "I'm") == ["i'm", "i", "am"]
