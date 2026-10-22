"""Tests for storage.translation_helpers.split_llm_language_batches.

An ancient language in a request adds a translation_status field for every
language in it, and a full batch mixing ancient and modern languages exceeded
OpenAI's schema size limit -- so every request for that batch failed.
"""

from __future__ import annotations

from storage.translation_helpers import (
    ANCIENT_LANGUAGE_GROUP,
    MAX_LLM_LANGUAGES_PER_OPERATION,
    split_llm_language_batches,
)

MODERN = ["vi", "ja", "ko", "sw", "ro", "pl", "th", "ms", "my", "km", "lo", "tl"]


def test_empty_input_gives_no_batches() -> None:
    assert split_llm_language_batches([]) == []


def test_modern_languages_keep_order_and_the_cap() -> None:
    batches = split_llm_language_batches(MODERN)

    assert batches == [MODERN[:MAX_LLM_LANGUAGES_PER_OPERATION], MODERN[10:]]


def test_ancient_languages_never_share_a_batch_with_modern_ones() -> None:
    interleaved = ["vi", "la", "ja", "sa", "ko", "grc", "sw", "ar-classical", "ro", "non"]

    batches = split_llm_language_batches(interleaved)

    assert batches == [["vi", "ja", "ko", "sw", "ro"], ANCIENT_LANGUAGE_GROUP]


def test_ancient_batches_come_after_the_modern_ones() -> None:
    batches = split_llm_language_batches(list(ANCIENT_LANGUAGE_GROUP) + MODERN)

    assert batches[-1] == ANCIENT_LANGUAGE_GROUP
    assert sum(len(batch) for batch in batches) == len(ANCIENT_LANGUAGE_GROUP) + len(MODERN)
    for batch in batches[:-1]:
        assert not set(batch) & set(ANCIENT_LANGUAGE_GROUP)
