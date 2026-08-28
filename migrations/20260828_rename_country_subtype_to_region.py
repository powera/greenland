#!/usr/bin/env python3
"""Rename the noun subtype ``country`` to ``region`` without changing GUIDs.

The N45 category contains countries, US states, and other political regions.
This migration updates the SQLite lemma rows, rewrites the subtype in the
release base records, and moves ``lemmas/nouns/country`` to
``lemmas/nouns/region``. It is safe to rerun after a successful migration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import constants
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.models.schema import Lemma

OLD_SUBTYPE = "country"
NEW_SUBTYPE = "region"
GUID_PREFIX = "N45_"
DEFAULT_RELEASE_ROOT = ROOT / "data" / "release"


@dataclass(frozen=True)
class MigrationResult:
    """Counts reported by one migration run."""

    database_rows_updated: int
    release_records_updated: int
    release_directory_moved: bool


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSON objects from a JSONL file."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as input_file:
        for line_number, raw_line in enumerate(input_file, start=1):
            stripped_line = raw_line.strip()
            if not stripped_line:
                continue
            decoded = json.loads(stripped_line)
            if not isinstance(decoded, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            records.append(decoded)
    return records


def _write_jsonl_atomic(path: Path, records: Sequence[dict[str, Any]]) -> None:
    """Atomically replace a JSONL file with ``records``."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        try:
            for record in records:
                temporary_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
    os.replace(temporary_path, path)


def _validate_release_records(records: Sequence[dict[str, Any]], path: Path) -> None:
    """Reject an unexpected category before changing release data."""
    for record in records:
        guid = record.get("guid")
        subtype = record.get("pos_subtype")
        if not isinstance(guid, str) or not guid.startswith(GUID_PREFIX):
            raise ValueError(f"{path}: unexpected GUID {guid!r}; expected {GUID_PREFIX}*")
        if subtype not in {OLD_SUBTYPE, NEW_SUBTYPE}:
            raise ValueError(f"{path}: unexpected pos_subtype {subtype!r}")


def migrate_release(release_root: Path, dry_run: bool = False) -> tuple[int, bool]:
    """Rewrite and move the release category, returning records changed and move status."""
    nouns_root = release_root / "lemmas" / "nouns"
    old_directory = nouns_root / OLD_SUBTYPE
    new_directory = nouns_root / NEW_SUBTYPE

    if old_directory.exists() and new_directory.exists():
        raise RuntimeError(
            f"Both {old_directory} and {new_directory} exist; refusing to merge them automatically"
        )

    source_directory = old_directory if old_directory.exists() else new_directory
    if not source_directory.exists():
        raise FileNotFoundError(
            f"Neither {old_directory} nor {new_directory} exists; release tree is incomplete"
        )

    base_path = source_directory / "base.jsonl"
    records = _read_jsonl(base_path)
    _validate_release_records(records, base_path)
    records_updated = sum(record.get("pos_subtype") == OLD_SUBTYPE for record in records)
    directory_moved = source_directory == old_directory

    if dry_run:
        return records_updated, directory_moved

    if records_updated:
        rewritten_records = [
            (
                {**record, "pos_subtype": NEW_SUBTYPE}
                if record.get("pos_subtype") == OLD_SUBTYPE
                else record
            )
            for record in records
        ]
        _write_jsonl_atomic(base_path, rewritten_records)

    if directory_moved:
        old_directory.rename(new_directory)

    return records_updated, directory_moved


def migrate_database(config: DataSourceConfig, dry_run: bool = False) -> int:
    """Update SQLite lemma subtypes and return the number of matching rows."""
    if config.backend_type != BackendType.SQLITE:
        raise ValueError("This one-off migration supports only the SQLite backend")

    session = create_session(config)
    try:
        country_query = session.query(Lemma).filter(
            Lemma.pos_type == "noun",
            Lemma.pos_subtype == OLD_SUBTYPE,
        )
        rows_updated = int(country_query.count())
        if rows_updated and not dry_run:
            country_query.update({Lemma.pos_subtype: NEW_SUBTYPE}, synchronize_session=False)
            session.commit()
        return rows_updated
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def run_migration(
    config: DataSourceConfig,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    dry_run: bool = False,
) -> MigrationResult:
    """Apply both release and database changes."""
    release_records_updated, release_directory_moved = migrate_release(
        release_root, dry_run=dry_run
    )
    database_rows_updated = migrate_database(config, dry_run=dry_run)
    return MigrationResult(
        database_rows_updated=database_rows_updated,
        release_records_updated=release_records_updated,
        release_directory_moved=release_directory_moved,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse command-line arguments and run the migration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        default=constants.WORDFREQ_DB_PATH,
        help="SQLite database to migrate (default: %(default)s)",
    )
    parser.add_argument(
        "--release-root",
        type=Path,
        default=DEFAULT_RELEASE_ROOT,
        help="Release root containing lemmas/nouns (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the changes without writing the database or release tree",
    )
    args = parser.parse_args(argv)

    config = DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=args.sqlite_path,
    )
    result = run_migration(config, release_root=args.release_root, dry_run=args.dry_run)
    action = "Would update" if args.dry_run else "Updated"
    move_action = "would move" if args.dry_run else "moved"
    already_moved = "already at region" if not result.release_directory_moved else move_action
    print(f"{action} {result.database_rows_updated} database lemma rows")
    print(f"{action} {result.release_records_updated} release base records")
    print(f"Release directory: {already_moved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
