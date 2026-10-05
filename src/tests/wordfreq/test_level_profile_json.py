"""Tests for saving, re-scoring and loading level corpus profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wordfreq.frequency.level_profile import (
    GENERAL,
    JSON_FORMAT_VERSION,
    load_level_profiles,
    profile_from_zipfs,
    profiles_from_json,
    profiles_to_json,
)

ZIPFS = {"arts": 5.0, "cooking": 3.0, "books": 3.0}


def test_saved_measurements_rescore_at_a_new_threshold() -> None:
    profile = profile_from_zipfs(7, "fresco", None, 330, ZIPFS, ["arts"], min_skew=0.5)
    assert profile.weights == {"arts": 1.0}  # skew 2.0

    saved = profiles_to_json([profile], {105: 2}, list(ZIPFS), 0.5)
    lemma_profiles, unattested, corpus_names = profiles_from_json(saved, min_skew=3.0)

    assert corpus_names == list(ZIPFS)
    assert unattested == {105: 2}
    assert lemma_profiles[0].lemma_text == "fresco"
    assert lemma_profiles[0].zipf_by_corpus == pytest.approx(ZIPFS)
    assert lemma_profiles[0].weights == {GENERAL: 1.0}


def test_from_json_filters_levels() -> None:
    profiles = [
        profile_from_zipfs(1, "fresco", None, 330, ZIPFS, ["arts"]),
        profile_from_zipfs(2, "simmer", None, 105, ZIPFS, ["arts"]),
    ]
    saved = profiles_to_json(profiles, {105: 1, 330: 1}, list(ZIPFS), 0.5)
    lemma_profiles, unattested, _ = profiles_from_json(saved, 0.5, levels=[330])
    assert [profile.level for profile in lemma_profiles] == [330]
    assert unattested == {330: 1}


def test_from_json_refuses_another_format_version() -> None:
    saved = profiles_to_json([], {}, list(ZIPFS), 0.5)
    saved["format_version"] = JSON_FORMAT_VERSION + 1
    with pytest.raises(ValueError):
        profiles_from_json(saved, 0.5)


def test_load_level_profiles_reads_a_saved_file(tmp_path: Path) -> None:
    profiles = [
        profile_from_zipfs(1, "fresco", None, 330, ZIPFS, ["arts"]),
        profile_from_zipfs(2, "unlevelled", None, None, ZIPFS, ["arts"]),
    ]
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(profiles_to_json(profiles, {105: 1}, list(ZIPFS), 0.5)))

    level_profiles, lemma_profiles = load_level_profiles(str(path))
    assert len(lemma_profiles) == 2
    assert sorted(level_profiles) == [105, 330]  # the unlevelled lemma joins no level
    assert level_profiles[330].share("arts") == pytest.approx(1.0)
    assert level_profiles[105].unattested_count == 1
