"""Tests for the major/minor SQLite backup tiers."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

import pytest

from storage import backup
from storage.backend.config import BackendType, DataSourceConfig
from storage.backup import BackupFile

NOW = datetime(2026, 10, 16, 12, 0)


def make_backup(name: str, hours_old: float, tier: str = "minor") -> BackupFile:
    return BackupFile(
        path=Path(name),
        tier=tier,  # type: ignore[arg-type]
        created=NOW - timedelta(hours=hours_old),
        size=0,
    )


def names(backups: List[BackupFile]) -> List[str]:
    return [item.path.name for item in backups]


@pytest.fixture()
def config(tmp_path: Path) -> DataSourceConfig:
    database = tmp_path / "linguistics.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE words (text TEXT)")
    connection.execute("INSERT INTO words VALUES ('labas')")
    connection.commit()
    connection.close()
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(database))


class TestSelectPrunable:
    def test_needs_both_age_and_five_newer(self) -> None:
        minors = [make_backup(f"old-{index}", 100 + index) for index in range(3)] + [
            make_backup(f"new-{index}", index) for index in range(5)
        ]
        assert sorted(names(backup.select_prunable(minors, NOW))) == ["old-0", "old-1", "old-2"]

    def test_old_backup_is_kept_with_only_four_newer(self) -> None:
        minors = [make_backup("old", 200)] + [make_backup(f"new-{i}", i) for i in range(4)]
        assert backup.select_prunable(minors, NOW) == []

    def test_young_backup_is_kept_however_many_are_newer(self) -> None:
        minors = [make_backup("young", 71)] + [make_backup(f"new-{i}", i) for i in range(10)]
        assert backup.select_prunable(minors, NOW) == []

    def test_ties_do_not_count_as_newer(self) -> None:
        tied = [make_backup(f"tied-{i}", 100) for i in range(6)]
        assert backup.select_prunable(tied, NOW) == []

    def test_majors_are_never_selected(self) -> None:
        mixed = [make_backup("major", 500, tier="major")] + [
            make_backup(f"new-{i}", i) for i in range(5)
        ]
        assert backup.select_prunable(mixed, NOW) == []


class TestCreateBackup:
    def test_copies_committed_wal_rows_into_the_tier_directory(
        self, config: DataSourceConfig, tmp_path: Path
    ) -> None:
        holder = sqlite3.connect(str(config.sqlite_path))
        holder.execute("PRAGMA wal_autocheckpoint=0")
        holder.execute("INSERT INTO words VALUES ('aciu')")
        holder.commit()
        try:
            path = backup.create_backup(config, "add-words", "major", today=date(2026, 10, 16))
        finally:
            holder.close()
        assert path == tmp_path / "backups" / "major" / "linguistics.sqlite.bak-20261016-add-words"
        copy = sqlite3.connect(path)
        assert copy.execute("SELECT count(*) FROM words").fetchone()[0] == 2
        copy.close()

    def test_same_day_and_label_gets_a_suffix(self, config: DataSourceConfig) -> None:
        first = backup.create_backup(config, "relevel", today=date(2026, 10, 16))
        second = backup.create_backup(config, "relevel", today=date(2026, 10, 16))
        assert first.parent.name == "minor"
        assert second.name == first.name + "-2"

    def test_rejects_labels_that_would_break_the_name(self, config: DataSourceConfig) -> None:
        with pytest.raises(ValueError):
            backup.create_backup(config, "../escape")

    def test_never_deletes_anything(self, config: DataSourceConfig) -> None:
        for index in range(7):
            backup.create_backup(config, f"step-{index}")
        assert len(backup.list_backups(config, "minor")) == 7


class TestPruneAndPromote:
    def test_prune_is_a_dry_run_unless_applied(
        self, config: DataSourceConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        created: Dict[str, datetime] = {}
        minors = []
        for index in range(7):
            path = backup.create_backup(config, f"step-{index}")
            created[path.name] = NOW - timedelta(hours=100 - index)
            minors.append(path)
        major = backup.create_backup(config, "keep-forever", "major")
        created[major.name] = NOW - timedelta(days=60)
        sidecar = minors[0].with_name(minors[0].name + "-shm")
        sidecar.write_bytes(b"")
        stray = backup.tier_dir(config, "minor") / "notes.txt"
        stray.write_text("not a backup")
        monkeypatch.setattr(backup, "_created", lambda path: created[path.name])

        would = backup.prune_minor_backups(config, now=NOW)
        assert len(would) == 2
        assert all(item.path.exists() for item in would)

        deleted = backup.prune_minor_backups(config, apply=True, now=NOW)
        assert names(deleted) == names(would)
        assert not any(item.path.exists() for item in deleted)
        assert not sidecar.exists()
        assert major.exists()
        assert stray.exists()
        assert len(backup.list_backups(config, "minor")) == 5

    def test_promote_moves_a_minor_backup_to_major(self, config: DataSourceConfig) -> None:
        minor = backup.create_backup(config, "drop-pending")
        promoted = backup.promote_backup(config, minor.name)
        assert promoted.parent.name == "major"
        assert promoted.exists() and not minor.exists()
