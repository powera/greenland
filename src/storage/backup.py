"""Archive copies of the SQLite database, in a major and a minor tier.

Every archive copy of the database is made here; nothing else should call
``sqlite3.Connection.backup`` or ``cp`` to take one.  The database runs in WAL
mode, so committed writes can sit in ``linguistics.sqlite-wal`` for days and a
plain file copy silently captures a stale snapshot.  The online-backup API used
here reads through the WAL and is safe while Barsukas or an agent holds the
database open.

Backups live beside the database in two directories::

    data/wordfreq/backups/major/linguistics.sqlite.bak-20261015-drop-pending
    data/wordfreq/backups/minor/linguistics.sqlite.bak-20261016-verb-forms

Major backups are kept indefinitely: take one before an irreversible structural
change (dropping a table, a rebuild, a bulk delete).  Minor backups are the
default, for routine "before I touch this" copies, and are eligible for pruning
once they are older than :data:`MINOR_MAX_AGE` *and* at least
:data:`MINOR_KEEP_NEWEST` other minor backups are strictly newer.  Majors never
count toward that number.  A backup tied on time with another never counts as
newer than it, so a tie keeps both.

Pruning only happens when ``prune`` is run with ``--apply``; creating a backup
never deletes one.

Age is the file's creation time (``st_birthtime``), falling back to its
modification time where the platform has no birth time.  Not ``st_ctime``: on
macOS that changes when a file is renamed or moved between the tier
directories.

TODO: decide whether ``create`` should prune automatically, after a trial week
(from 2026-10-16) of seeing how many backups a normal week produces.
TODO: analyze zstd compression for major backups -- the size saved against the
decompress step it adds before any restore.

Usage::

    PYTHONPATH=src python -m storage.backup create --label verb-forms
    PYTHONPATH=src python -m storage.backup create --tier major --label drop-pending
    PYTHONPATH=src python -m storage.backup list
    PYTHONPATH=src python -m storage.backup prune            # dry run
    PYTHONPATH=src python -m storage.backup prune --apply
    PYTHONPATH=src python -m storage.backup promote linguistics.sqlite.bak-20261016-verb-forms
"""

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Literal, Optional, Sequence

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.backend.config import BackendType, DataSourceConfig

Tier = Literal["major", "minor"]
TIERS: Sequence[Tier] = ("major", "minor")

BACKUP_DIR_NAME = "backups"
MINOR_MAX_AGE = timedelta(hours=72)
MINOR_KEEP_NEWEST = 5

# WAL-mode files SQLite leaves beside a backup that something has opened.
SIDECAR_SUFFIXES = ("-wal", "-shm")

_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class BackupFile:
    """One archived copy of the database."""

    path: Path
    tier: Tier
    created: datetime
    size: int


def database_path(config: DataSourceConfig) -> Path:
    """The SQLite file a config points at, or an error for other backends."""
    if config.backend_type != BackendType.SQLITE or not config.sqlite_path:
        raise ValueError("Backups need a SQLite configuration")
    return Path(config.sqlite_path).resolve()


def backup_root(config: DataSourceConfig) -> Path:
    """The ``backups/`` directory beside the database."""
    return database_path(config).parent / BACKUP_DIR_NAME


def tier_dir(config: DataSourceConfig, tier: Tier) -> Path:
    """The directory holding one tier's backups."""
    return backup_root(config) / tier


def _backup_prefix(config: DataSourceConfig) -> str:
    return f"{database_path(config).name}.bak-"


def _unused_path(directory: Path, name: str) -> Path:
    """``name`` in ``directory``, suffixed ``-2``, ``-3``... if already taken."""
    candidate = directory / name
    counter = 2
    while candidate.exists():
        candidate = directory / f"{name}-{counter}"
        counter += 1
    return candidate


def create_backup(
    config: DataSourceConfig,
    label: str,
    tier: Tier = "minor",
    *,
    today: Optional[date] = None,
) -> Path:
    """Write a WAL-consistent copy of the database into the tier's directory.

    The name is ``<db>.bak-YYYYMMDD-<label>``; a second backup with the same
    date and label gets a ``-2`` suffix rather than replacing the first.
    Nothing is deleted.
    """
    if tier not in TIERS:
        raise ValueError(f"Unknown backup tier: {tier!r}")
    if not _LABEL_PATTERN.match(label):
        raise ValueError(f"Backup label must be lowercase letters, digits and hyphens: {label!r}")
    source = database_path(config)
    if not source.is_file():
        raise FileNotFoundError(f"No database to back up at {source}")

    directory = tier_dir(config, tier)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (today or date.today()).strftime("%Y%m%d")
    destination = _unused_path(directory, f"{_backup_prefix(config)}{stamp}-{label}")

    source_connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    try:
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()
    return destination


def _created(path: Path) -> datetime:
    stat = path.stat()
    timestamp = getattr(stat, "st_birthtime", None) or stat.st_mtime
    return datetime.fromtimestamp(timestamp)


def _is_backup_name(name: str, prefix: str) -> bool:
    return name.startswith(prefix) and not name.endswith(SIDECAR_SUFFIXES)


def list_backups(config: DataSourceConfig, tier: Optional[Tier] = None) -> List[BackupFile]:
    """Backups in one tier (or both), oldest first."""
    prefix = _backup_prefix(config)
    found: List[BackupFile] = []
    for current_tier in [tier] if tier else TIERS:
        directory = tier_dir(config, current_tier)
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_file() and _is_backup_name(path.name, prefix):
                found.append(
                    BackupFile(
                        path=path,
                        tier=current_tier,
                        created=_created(path),
                        size=path.stat().st_size,
                    )
                )
    return sorted(found, key=lambda backup: (backup.created, backup.path.name))


def newer_count(backup: BackupFile, others: Sequence[BackupFile]) -> int:
    """How many of ``others`` are strictly newer than ``backup``."""
    return sum(other.created > backup.created for other in others)


def select_prunable(
    minors: Sequence[BackupFile],
    now: datetime,
    *,
    max_age: timedelta = MINOR_MAX_AGE,
    keep_newest: int = MINOR_KEEP_NEWEST,
) -> List[BackupFile]:
    """The retention rule: older than ``max_age`` and ``keep_newest`` strictly newer."""
    return [
        backup
        for backup in minors
        if backup.tier == "minor"
        and now - backup.created > max_age
        and newer_count(backup, minors) >= keep_newest
    ]


def prunable_minor_backups(
    config: DataSourceConfig, *, now: Optional[datetime] = None
) -> List[BackupFile]:
    """Minor backups the retention rule allows deleting; majors never appear."""
    return select_prunable(list_backups(config, "minor"), now or datetime.now())


def prune_minor_backups(
    config: DataSourceConfig,
    *,
    apply: bool = False,
    now: Optional[datetime] = None,
) -> List[BackupFile]:
    """Return the prunable minor backups, deleting them (and sidecars) only if ``apply``."""
    doomed = prunable_minor_backups(config, now=now)
    if apply:
        for backup in doomed:
            for suffix in SIDECAR_SUFFIXES:
                sidecar = backup.path.with_name(backup.path.name + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            backup.path.unlink()
    return doomed


def promote_backup(config: DataSourceConfig, name: str) -> Path:
    """Move a minor backup into the major tier, keeping its name and times."""
    source = tier_dir(config, "minor") / name
    if not source.is_file() or not _is_backup_name(name, _backup_prefix(config)):
        raise FileNotFoundError(f"No minor backup named {name}")
    major = tier_dir(config, "major")
    major.mkdir(parents=True, exist_ok=True)
    destination = major / name
    if destination.exists():
        raise FileExistsError(f"A major backup named {name} already exists")
    source.rename(destination)
    for suffix in SIDECAR_SUFFIXES:
        sidecar = source.with_name(name + suffix)
        if sidecar.exists():
            sidecar.rename(major / (name + suffix))
    return destination


def _format_size(size: int) -> str:
    return f"{size / 1_000_000:,.0f} MB"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create, list, prune and promote DB backups.")
    parser.add_argument("--db-path", help="SQLite database (default: the configured one)")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Back up the database")
    create.add_argument("--label", required=True, help="10-20 chars naming the task")
    create.add_argument("--tier", choices=TIERS, default="minor")

    commands.add_parser("list", help="List backups in both tiers")

    prune = commands.add_parser("prune", help="Delete minor backups past retention")
    prune.add_argument("--apply", action="store_true", help="Delete; otherwise only report")

    promote = commands.add_parser("promote", help="Move a minor backup to the major tier")
    promote.add_argument("name", help="File name inside backups/minor/")

    args = parser.parse_args(argv)
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)

    if args.command == "create":
        print(f"Backup: {create_backup(config, args.label, args.tier)}")
    elif args.command == "list":
        minors = list_backups(config, "minor")
        prunable = {backup.path for backup in prunable_minor_backups(config)}
        for backup in list_backups(config):
            note = ""
            if backup.tier == "minor":
                note = f"{newer_count(backup, minors)} newer"
                if backup.path in prunable:
                    note += ", prunable"
            print(
                f"{backup.tier:5}  {backup.created:%Y-%m-%d %H:%M}  "
                f"{_format_size(backup.size):>9}  {backup.path.name}  {note}"
            )
    elif args.command == "prune":
        doomed = prune_minor_backups(config, apply=args.apply)
        verb = "Deleted" if args.apply else "Would delete"
        for backup in doomed:
            print(f"{verb} {backup.path.name} ({backup.created:%Y-%m-%d %H:%M})")
        print(f"{verb} {len(doomed)} minor backup(s)")
    elif args.command == "promote":
        print(f"Promoted: {promote_backup(config, args.name)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
