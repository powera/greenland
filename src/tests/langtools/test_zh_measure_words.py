"""Stored-string <-> list handling for the zh measure-word list facts."""

import pytest

from langtools.zh.measure_words import (
    format_measure_word_list,
    measure_word_lists,
    parse_measure_word_list,
)


def test_format_deduplicates_drops_primary_and_keeps_order() -> None:
    assert format_measure_word_list([" 张 ", "把", "个", "张", ""], exclude="把") == "张, 个"


def test_format_empty_is_none() -> None:
    assert format_measure_word_list([]) == "none"
    assert format_measure_word_list(["把"], exclude="把") == "none"


@pytest.mark.parametrize("item", ["一只", "两张", "zhāng", "3个", "一", "个 (alt: 只)", "四个字的"])
def test_format_rejects_non_classifiers(item: str) -> None:
    with pytest.raises(ValueError):
        format_measure_word_list([item])


@pytest.mark.parametrize("item", ["千克", "两", "个月"])
def test_units_that_start_like_numerals_are_allowed(item: str) -> None:
    assert format_measure_word_list([item]) == item


def test_parse_distinguishes_unchecked_from_none() -> None:
    assert parse_measure_word_list(None) is None
    assert parse_measure_word_list("") is None
    assert parse_measure_word_list("none") == []
    assert parse_measure_word_list("张, 个") == ["张", "个"]
    assert parse_measure_word_list("张、个") == ["张", "个"]


def test_lists_only_include_checked_facts() -> None:
    facts = {"measure_words": "碗", "measure_words_portions": "none"}
    assert measure_word_lists(facts) == {"measure_words_portions": []}
