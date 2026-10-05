"""Tests for the level corpus-profile report's saved-measurement round trip."""

from __future__ import annotations

import pytest

from wordfreq.frequency.level_profile import GENERAL, profile_from_zipfs
from wordfreq.tools.level_corpus_profile import JSON_FORMAT_VERSION, from_json, to_json

ZIPFS = {"arts": 5.0, "cooking": 3.0, "books": 3.0}


def test_saved_measurements_rescore_at_a_new_threshold() -> None:
    profile = profile_from_zipfs(7, "fresco", None, 330, ZIPFS, ["arts"], min_skew=0.5)
    assert profile.weights == {"arts": 1.0}  # skew 2.0

    saved = to_json([profile], {105: 2}, list(ZIPFS), 0.5)
    lemma_profiles, unattested, corpus_names = from_json(saved, min_skew=3.0)

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
    saved = to_json(profiles, {105: 1, 330: 1}, list(ZIPFS), 0.5)
    lemma_profiles, unattested, _ = from_json(saved, 0.5, levels=[330])
    assert [profile.level for profile in lemma_profiles] == [330]
    assert unattested == {330: 1}


def test_from_json_refuses_another_format_version() -> None:
    saved = to_json([], {}, list(ZIPFS), 0.5)
    saved["format_version"] = JSON_FORMAT_VERSION + 1
    with pytest.raises(ValueError):
        from_json(saved, 0.5)
