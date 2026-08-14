from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from storage.admin.bootstrap import bootstrap_empty_database, bootstrap_from_release
from storage.admin.service import DatabaseAdminService
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Lemma


def test_empty_bootstrap_delegates_for_empty_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.sqlite"
    config = DataSourceConfig(sqlite_path=str(database_path))
    expected = {"duration_seconds": 0.0}

    with patch.object(DatabaseAdminService, "initialize_database", return_value=expected):
        result = bootstrap_empty_database(config)

    assert result["bootstrap_kind"] == "empty"
    assert result["database_path"] == str(database_path)


def test_empty_bootstrap_rejects_database_with_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "populated.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("CREATE TABLE marker (value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('existing')")
        connection.commit()
    finally:
        connection.close()

    config = DataSourceConfig(sqlite_path=str(database_path))
    with pytest.raises(ValueError, match="already contains data"):
        bootstrap_empty_database(config)


def test_empty_bootstrap_dry_run_does_not_create_database(tmp_path: Path) -> None:
    database_path = tmp_path / "dry-run.sqlite"
    config = DataSourceConfig(sqlite_path=str(database_path))

    result = bootstrap_empty_database(config, dry_run=True)

    assert result["steps"][0] == "create_schema"
    assert not database_path.exists()


def test_bootstrap_from_release_builds_sqlite(tmp_path: Path) -> None:
    release_path = tmp_path / "release"
    category_path = release_path / "lemmas" / "nouns" / "animal"
    category_path.mkdir(parents=True)
    record = {
        "guid": "N01_001",
        "pos_type": "noun",
        "pos_subtype": "animal",
        "concept_label": "dog",
        "concept_definition": "a domesticated canine",
        "translations": {"en": "dog", "lt": "šuo"},
        "difficulty_level": 1,
    }
    (category_path / "base.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    database_path = tmp_path / "from-release.sqlite"
    config = DataSourceConfig(sqlite_path=str(database_path))
    result = bootstrap_from_release(config, release_path, include_frequency_data=False)

    assert result["imported_components"] == ["jsonl"]
    session = create_session(config)
    try:
        lemma = session.query(Lemma).filter(Lemma.guid == "N01_001").one()
        assert lemma.lemma_text == "dog"
    finally:
        session.close()


def test_bootstrap_requires_sqlite_config(tmp_path: Path) -> None:
    release_path = tmp_path / "release"
    (release_path / "lemmas").mkdir(parents=True)
    config = DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir=str(release_path))

    with pytest.raises(ValueError, match="SQLite DataSourceConfig"):
        bootstrap_from_release(config, release_path)
