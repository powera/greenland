"""Tests for the release-derived proper-noun vocabulary whitelist."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Sequence

from wordfreq.corpora.proper_noun_vocabulary import (
    AMBIGUOUS_WITH_COMMON_WORDS,
    VOCABULARY_NAME_SUBTYPES,
    excluded_words,
    load_always_vocabulary,
    load_always_vocabulary_by_subtype,
)


def _write_subtype(root: Path, subtype: str, forms_by_guid: Dict[str, Sequence[str]]) -> None:
    """Write a minimal ``en.jsonl`` for one noun subtype."""
    directory = root / "lemmas" / "nouns" / subtype
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "en.jsonl", "w", encoding="utf-8") as handle:
        for guid, forms in forms_by_guid.items():
            record = {
                "guid": guid,
                "forms": [{"grammatical_form": "noun/en_singular", "text": text} for text in forms],
            }
            handle.write(json.dumps(record) + "\n")


def test_days_and_months_are_kept_as_vocabulary(tmp_path: Path) -> None:
    """The words the capitalization filter would otherwise eat."""
    _write_subtype(
        tmp_path,
        "temporal_name",
        {"N32_001": ["Monday"], "N32_006": ["Saturday"], "N32_008": ["January"]},
    )

    words = load_always_vocabulary(subtypes=["temporal_name"], release_dir=str(tmp_path))
    assert words == ("january", "monday", "saturday")


def test_ambiguous_month_names_are_held_back(tmp_path: Path) -> None:
    """ "May" as a whitelist entry would credit the month with the modal verb."""
    _write_subtype(
        tmp_path,
        "temporal_name",
        {"N32_010": ["March"], "N32_012": ["May"], "N32_006": ["Saturday"]},
    )

    words = load_always_vocabulary(subtypes=["temporal_name"], release_dir=str(tmp_path))
    assert words == ("saturday",)
    assert "may" not in words
    assert "march" not in words

    held = excluded_words(subtypes=["temporal_name"], release_dir=str(tmp_path))
    assert set(held) == {"march", "may"}


def test_multiword_names_are_kept_whole(tmp_path: Path) -> None:
    """Splitting "New York" would whitelist "new" -- an ordinary English word."""
    _write_subtype(tmp_path, "city", {"N46_008": ["New York"], "N46_010": ["Los Angeles"]})

    words = load_always_vocabulary(subtypes=["city"], release_dir=str(tmp_path))
    assert words == ("los angeles", "new york")
    for fragment in ("new", "york", "los", "angeles"):
        assert fragment not in words


def test_lowercase_entries_are_skipped(tmp_path: Path) -> None:
    """An uncapitalized entry is never filtered as a name, so it is a no-op."""
    _write_subtype(tmp_path, "city", {"N46_001": ["Warsaw"], "N46_002": ["area"]})

    words = load_always_vocabulary(subtypes=["city"], release_dir=str(tmp_path))
    assert words == ("warsaw",)


def test_inflected_forms_are_all_collected(tmp_path: Path) -> None:
    """Every English form of a name enters, not just the base form."""
    _write_subtype(tmp_path, "geographic_place", {"N56_010": ["Alps", "Alp"]})

    words = load_always_vocabulary(subtypes=["geographic_place"], release_dir=str(tmp_path))
    assert words == ("alp", "alps")


def test_missing_subtype_file_yields_nothing(tmp_path: Path) -> None:
    """A subtype with no en.jsonl is skipped rather than raising."""
    (tmp_path / "lemmas" / "nouns").mkdir(parents=True, exist_ok=True)

    assert load_always_vocabulary(subtypes=["personal_name"], release_dir=str(tmp_path)) == ()


def test_malformed_json_line_is_skipped(tmp_path: Path) -> None:
    """One bad line does not lose the rest of the file."""
    directory = tmp_path / "lemmas" / "nouns" / "city"
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "en.jsonl", "w", encoding="utf-8") as handle:
        handle.write("{not json}\n")
        handle.write(
            json.dumps(
                {"guid": "N46_001", "forms": [{"text": "Warsaw"}]},
            )
            + "\n"
        )

    words = load_always_vocabulary(subtypes=["city"], release_dir=str(tmp_path))
    assert words == ("warsaw",)


def test_by_subtype_keeps_categories_apart(tmp_path: Path) -> None:
    _write_subtype(tmp_path, "temporal_name", {"N32_006": ["Saturday"]})
    _write_subtype(tmp_path, "city", {"N46_001": ["Warsaw"]})

    by_subtype = load_always_vocabulary_by_subtype(
        subtypes=["temporal_name", "city"], release_dir=str(tmp_path)
    )
    assert by_subtype == {"temporal_name": ("saturday",), "city": ("warsaw",)}


def test_place_name_is_not_a_default_subtype() -> None:
    """``place_name`` holds common nouns (area, city), not capitalized names."""
    assert "place_name" not in VOCABULARY_NAME_SUBTYPES
    assert "temporal_name" in VOCABULARY_NAME_SUBTYPES


def test_real_release_gives_the_priority_categories() -> None:
    """Against the checked-in release tree: days and months are covered."""
    words = load_always_vocabulary()
    for day in ("monday", "saturday", "sunday"):
        assert day in words
    for month in ("january", "june", "december"):
        assert month in words
    # Cities land at the same time, per the stated priority.
    assert "london" in words
    assert "paris" in words
    # ...and the ambiguous ones stay out.
    assert AMBIGUOUS_WITH_COMMON_WORDS.isdisjoint(words)


def test_real_release_has_no_bare_fragments_of_multiword_names() -> None:
    """A regression guard: "new", "year" and "states" must never appear."""
    words = set(load_always_vocabulary())
    for fragment in ("new", "year", "day", "states", "united", "sea", "ocean"):
        assert fragment not in words
