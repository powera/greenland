from pathlib import Path

import constants
from storage.backend.config import BackendType, DataSourceConfig
from exports.wireword.export_wireword import (
    LANGUAGE_EXPORT_MAX_LEVELS,
    WirewordExporter,
    decoy_pool_name,
)


def test_language_export_max_levels_cover_full_curricula() -> None:
    assert LANGUAGE_EXPORT_MAX_LEVELS == {
        "lt": 64,
        "es": 30,
        "fr": 30,
        "zh": constants.TOPIC_DIFFICULTY_LEVEL_MIN - 1,
    }


def test_level_ranges_for_zh_stop_below_topic_band() -> None:
    exporter = WirewordExporter(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language="zh",
    )

    ranges = exporter._get_level_ranges()

    assert ranges[0] == (1, 5)
    assert (96, 99) in ranges
    assert (100, 124) in ranges
    assert (125, 149) in ranges
    assert ranges[-1] == (975, 999)


def test_level_ranges_for_lt_stay_five_wide() -> None:
    exporter = WirewordExporter(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language="lt",
    )

    ranges = exporter._get_level_ranges()

    assert ranges[0] == (1, 5)
    assert ranges[-1] == (61, 64)
    assert all(end - start < 5 for start, end in ranges)


def test_decoy_pool_name_follows_level_files_for_non_verbs() -> None:
    assert decoy_pool_name(1, is_verb=False) == "Levels 1-5"
    assert decoy_pool_name(5, is_verb=False) == "Levels 1-5"
    assert decoy_pool_name(6, is_verb=False) == "Levels 6-10"
    assert decoy_pool_name(20, is_verb=False) == "Levels 16-20"
    assert decoy_pool_name(100, is_verb=False) == "Levels 100-124"
    assert decoy_pool_name(124, is_verb=False) == "Levels 100-124"
    assert decoy_pool_name(125, is_verb=False) == "Levels 125-149"
    assert decoy_pool_name(499, is_verb=False) == "Levels 475-499"


def test_decoy_pool_name_pools_verbs_apart() -> None:
    assert decoy_pool_name(1, is_verb=True) == "Core Verbs"
    assert decoy_pool_name(20, is_verb=True) == "Core Verbs"
    assert decoy_pool_name(100, is_verb=True) == "Verbs 100-199"
    assert decoy_pool_name(199, is_verb=True) == "Verbs 100-199"
    assert decoy_pool_name(200, is_verb=True) == "Verbs 200-299"


def test_decoy_pool_names_never_look_like_sentence_corpora() -> None:
    # The web app treats any corpus containing "sentence" as sentences.
    names = {
        decoy_pool_name(level, is_verb) for level in range(1, 1000) for is_verb in (True, False)
    }
    assert not any("sentence" in name.lower() for name in names)


def test_remove_stale_level_files_keeps_written_and_other_files(tmp_path: Path) -> None:
    for name in (
        "wireword_levels_1_5.json",
        "wireword_levels_21_25.json",
        "wireword_manifest_v2.json",
        "wireword_sentences.json",
    ):
        (tmp_path / name).write_text("[]", encoding="utf-8")

    removed = WirewordExporter._remove_stale_level_files(
        str(tmp_path), {"wireword_levels_1_5.json"}
    )

    assert removed == ["wireword_levels_21_25.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "wireword_levels_1_5.json",
        "wireword_manifest_v2.json",
        "wireword_sentences.json",
    ]


def test_format_missing_verb_translation_warning_preview_and_count() -> None:
    exporter = WirewordExporter(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language="lt",
    )

    missing_forms = [
        (1480, "give", "verb/lt_1p_future"),
        (1481, "take", "verb/lt_3s_past"),
    ]

    message = exporter._format_missing_verb_translation_warning(missing_forms)

    assert "Found 2 missing form(s)." in message
    assert "lemma_id=1480" in message
    assert "lemma_text='give'" in message
    assert "grammatical_form='verb/lt_1p_future'" in message
    assert "Falling back to generated English labels" in message


def test_format_missing_verb_translation_warning_truncates_preview() -> None:
    exporter = WirewordExporter(
        config=DataSourceConfig(backend_type=BackendType.SQLITE),
        language="lt",
    )

    missing_forms = [(1000 + i, f"lemma{i}", f"verb/lt_{i}_future") for i in range(12)]

    message = exporter._format_missing_verb_translation_warning(missing_forms)

    assert "Found 12 missing form(s)." in message
    assert "... and 2 more missing forms" in message
