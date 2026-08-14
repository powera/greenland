"""Explicit bootstrap workflows for SQLite linguistic databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from storage.admin.service import DatabaseAdminService
from storage.backend.config import BackendType, DataSourceConfig
from storage.migrate import (
    import_idiom_release_to_sqlite,
    import_jsonl_to_sqlite,
    import_lemma_audio_release_to_sqlite,
)


def _sqlite_path(config: DataSourceConfig) -> Path:
    """Return the configured SQLite path or reject an incompatible backend."""
    if config.backend_type != BackendType.SQLITE or config.sqlite_path is None:
        raise ValueError("Database bootstrap requires a SQLite DataSourceConfig")
    return Path(config.sqlite_path)


def _database_has_rows(database_path: Path) -> bool:
    """Return whether an existing SQLite database contains application data."""
    if not database_path.exists() or database_path.stat().st_size == 0:
        return False

    connection = sqlite3.connect(str(database_path))
    try:
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
            if row[0] not in {"alembic_version"}
        ]
        for table_name in table_names:
            quoted_table_name = table_name.replace('"', '""')
            row = connection.execute(f'SELECT 1 FROM "{quoted_table_name}" LIMIT 1').fetchone()
            if row is not None:
                return True
        return False
    finally:
        connection.close()


def _require_empty_database(config: DataSourceConfig) -> Path:
    """Validate that an empty-database workflow will not modify existing data."""
    database_path = _sqlite_path(config)
    if _database_has_rows(database_path):
        raise ValueError(
            f"Target SQLite database '{database_path}' already contains data; "
            "empty-database bootstrap will not modify it"
        )
    return database_path


def bootstrap_empty_database(config: DataSourceConfig, *, dry_run: bool = False) -> dict[str, Any]:
    """Create schema and load corpus, tier, and rank data into an empty database."""
    database_path = _require_empty_database(config)
    if dry_run:
        return {
            "bootstrap_kind": "empty",
            "database_path": str(database_path),
            "dry_run": True,
            "steps": [
                "create_schema",
                "sync_corpus_configurations",
                "load_corpora",
                "import_tiers",
                "calculate_ranks",
            ],
        }
    service = DatabaseAdminService(config)
    result = service.initialize_database()
    result["bootstrap_kind"] = "empty"
    result["database_path"] = str(database_path)
    return result


def bootstrap_from_release(
    config: DataSourceConfig,
    release_path: Path,
    *,
    force: bool = False,
    include_frequency_data: bool = True,
) -> dict[str, Any]:
    """Build SQLite from a data/release-style JSONL tree.

    By default the imported release data is enriched with the local corpus and
    tier sources and receives freshly calculated combined ranks. Set
    ``include_frequency_data`` to false when an exact release-only database is
    required.
    """
    database_path = _sqlite_path(config)
    resolved_release_path = release_path.resolve()
    if not resolved_release_path.is_dir():
        raise ValueError(f"Release path does not exist: {resolved_release_path}")
    lemma_path = resolved_release_path / "lemmas"
    if not lemma_path.is_dir():
        raise ValueError(f"Release path must contain a lemmas/ directory: {resolved_release_path}")
    if not any(lemma_path.rglob("base.jsonl")):
        raise ValueError(
            f"Release path contains no lemma base.jsonl files: {resolved_release_path}"
        )

    import_jsonl_to_sqlite(
        str(resolved_release_path),
        str(database_path),
        force=force,
    )

    imported_components = ["jsonl"]
    idiom_path = resolved_release_path / "idioms"
    if (idiom_path / "base.jsonl").is_file():
        import_idiom_release_to_sqlite(str(database_path), str(idiom_path))
        imported_components.append("idioms")

    if any(lemma_path.rglob("audio.jsonl")):
        import_lemma_audio_release_to_sqlite(str(database_path), str(lemma_path))
        imported_components.append("lemma_audio")

    result: dict[str, Any] = {
        "bootstrap_kind": "release",
        "database_path": str(database_path),
        "release_path": str(resolved_release_path),
        "frequency_data_loaded": include_frequency_data,
        "imported_components": imported_components,
    }
    if not include_frequency_data:
        return result

    service = DatabaseAdminService(config)
    result["config_sync"] = service.sync_configurations()
    result["corpus_load"] = service.load_corpora()
    result["tier_import"] = service.import_tiers()
    result["rank_calculation"] = service.calculate_ranks()
    return result
