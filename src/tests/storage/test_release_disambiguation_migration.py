"""Tests for the dated release disambiguation migration."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = PROJECT_ROOT / "migrations" / "20260830_backfill_release_disambiguation.py"


def _load_migration() -> ModuleType:
    module_name = "migration_20260830_backfill_release_disambiguation"
    spec = importlib.util.spec_from_file_location(module_name, MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_release_fixture(release_root: Path, records: List[Dict[str, Any]]) -> Path:
    category = release_root / "lemmas" / "adjectives" / "quality"
    category.mkdir(parents=True)
    base_path = category / "base.jsonl"
    base_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return base_path


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _default_records() -> List[Dict[str, Any]]:
    return [
        {
            "guid": "A05_001",
            "pos_type": "adjective",
            "pos_subtype": "quality",
            "concept_label": "fine (quality)",
            "translations": {"en": "fine"},
            "translation_disambiguations": {"lt": "kokybe"},
            "difficulty_level": 5,
        },
        {
            "guid": "A05_002",
            "pos_type": "adjective",
            "pos_subtype": "quality",
            "concept_label": "good",
            "translations": {"en": "good"},
            "difficulty_level": 9,
        },
    ]


def test_the_parenthetical_becomes_the_en_entry(tmp_path: Path) -> None:
    base_path = _write_release_fixture(tmp_path, _default_records())
    migration = _load_migration()

    migration.run_migration(release_root=tmp_path)

    assert _read_jsonl(base_path)[0]["disambiguation"]["en"] == "quality"


def test_the_legacy_key_is_folded_in_and_removed(tmp_path: Path) -> None:
    base_path = _write_release_fixture(tmp_path, _default_records())
    migration = _load_migration()

    result = migration.run_migration(release_root=tmp_path)

    record = _read_jsonl(base_path)[0]
    assert record["disambiguation"] == {"lt": "kokybe", "en": "quality"}
    assert "translation_disambiguations" not in record
    assert result.legacy_keys_folded == 1


def test_the_concept_label_is_left_alone(tmp_path: Path) -> None:
    """The label keeps its parenthetical as display text."""
    base_path = _write_release_fixture(tmp_path, _default_records())
    migration = _load_migration()

    migration.run_migration(release_root=tmp_path)

    assert _read_jsonl(base_path)[0]["concept_label"] == "fine (quality)"


def test_a_record_without_a_sense_is_untouched(tmp_path: Path) -> None:
    base_path = _write_release_fixture(tmp_path, _default_records())
    migration = _load_migration()

    migration.run_migration(release_root=tmp_path)

    assert "disambiguation" not in _read_jsonl(base_path)[1]


def test_the_new_key_lands_where_the_legacy_one_was(tmp_path: Path) -> None:
    """A migrated line must match one written by the exporter."""
    base_path = _write_release_fixture(tmp_path, _default_records())
    migration = _load_migration()

    migration.run_migration(release_root=tmp_path)

    keys = list(_read_jsonl(base_path)[0])
    assert keys == [
        "guid",
        "pos_type",
        "pos_subtype",
        "concept_label",
        "translations",
        "disambiguation",
        "difficulty_level",
    ]


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    base_path = _write_release_fixture(tmp_path, _default_records())
    before = base_path.read_text(encoding="utf-8")
    migration = _load_migration()

    result = migration.run_migration(release_root=tmp_path, dry_run=True)

    assert result.records_updated == 1
    assert base_path.read_text(encoding="utf-8") == before


def test_rerunning_changes_nothing(tmp_path: Path) -> None:
    base_path = _write_release_fixture(tmp_path, _default_records())
    migration = _load_migration()

    migration.run_migration(release_root=tmp_path)
    after_first = base_path.read_text(encoding="utf-8")
    second = migration.run_migration(release_root=tmp_path)

    assert second.records_updated == 0
    assert second.records_already_set == 1
    assert base_path.read_text(encoding="utf-8") == after_first


def test_a_disagreeing_entry_is_reported_not_overwritten(tmp_path: Path) -> None:
    records = _default_records()
    records[0]["disambiguation"] = {"en": "excellence"}
    base_path = _write_release_fixture(tmp_path, records)
    migration = _load_migration()

    result = migration.run_migration(release_root=tmp_path)

    assert result.conflicts
    assert "A05_001" in result.conflicts[0]
    assert _read_jsonl(base_path)[0]["disambiguation"]["en"] == "excellence"


def test_a_conflict_exits_nonzero(tmp_path: Path) -> None:
    records = _default_records()
    records[0]["disambiguation"] = {"en": "excellence"}
    _write_release_fixture(tmp_path, records)
    migration = _load_migration()

    assert migration.main(["--release-root", str(tmp_path)]) == 1


def test_a_clean_run_exits_zero(tmp_path: Path) -> None:
    _write_release_fixture(tmp_path, _default_records())
    migration = _load_migration()

    assert migration.main(["--release-root", str(tmp_path)]) == 0
