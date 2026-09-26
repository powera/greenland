from pathlib import Path

import constants
from storage.backend.config import BackendType, DataSourceConfig
from exports.wireword.export_wireword import LANGUAGE_EXPORT_MAX_LEVELS, WirewordExporter


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
