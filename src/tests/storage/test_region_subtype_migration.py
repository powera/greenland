"""Tests for the dated country-to-region subtype migration."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from storage.backend import BackendType, DataSourceConfig, create_session
from storage.models.schema import Lemma

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = PROJECT_ROOT / "migrations" / "20260828_rename_country_subtype_to_region.py"


def _load_migration() -> ModuleType:
    module_name = "migration_20260828_rename_country_subtype_to_region"
    spec = importlib.util.spec_from_file_location(module_name, MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_release_fixture(release_root: Path) -> None:
    country_directory = release_root / "lemmas" / "nouns" / "country"
    country_directory.mkdir(parents=True)
    base_record = {
        "guid": "N45_001",
        "pos_type": "noun",
        "pos_subtype": "country",
        "concept_label": "Lithuania",
        "concept_definition": "a country in Europe",
        "translations": {"en": "Lithuania"},
        "difficulty_level": 1,
    }
    (country_directory / "base.jsonl").write_text(json.dumps(base_record) + "\n", encoding="utf-8")
    (country_directory / "secondary.jsonl").write_text(
        '{"guid": "N45_001", "translations": {}}\n', encoding="utf-8"
    )


def test_migration_renames_database_and_release_subtype_idempotently(tmp_path: Path) -> None:
    migration = _load_migration()
    config = DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=str(tmp_path / "linguistics.sqlite"),
    )
    session = create_session(config)
    session.add(
        Lemma(
            lemma_text="Lithuania",
            definition_text="a country in Europe",
            pos_type="noun",
            pos_subtype="country",
            guid="N45_001",
        )
    )
    session.commit()
    session.close()

    release_root = tmp_path / "release"
    _write_release_fixture(release_root)

    first_result: Any = migration.run_migration(config, release_root=release_root)
    assert first_result.database_rows_updated == 1
    assert first_result.release_records_updated == 1
    assert first_result.release_directory_moved is True

    assert not (release_root / "lemmas" / "nouns" / "country").exists()
    region_directory = release_root / "lemmas" / "nouns" / "region"
    assert (region_directory / "secondary.jsonl").exists()
    release_record = json.loads(
        (region_directory / "base.jsonl").read_text(encoding="utf-8").strip()
    )
    assert release_record["pos_subtype"] == "region"
    assert release_record["guid"] == "N45_001"

    verification_session = create_session(config)
    migrated_lemma = verification_session.query(Lemma).filter_by(guid="N45_001").one()
    assert migrated_lemma.pos_subtype == "region"
    verification_session.close()

    second_result: Any = migration.run_migration(config, release_root=release_root)
    assert second_result.database_rows_updated == 0
    assert second_result.release_records_updated == 0
    assert second_result.release_directory_moved is False
