#!/usr/bin/env python3
"""
Migration: Add ``names.guid`` and backfill it for existing names.

Names are now exported to ``data/release/names`` (their per-language renderings
- Džordžas, 乔治, ジョージ - are content that has to stay stable across every
text that uses a name), which means they need a release GUID like every other
exported element. The prefix encodes the name's kind; see
``storage.models.guid_prefixes.NAME_KIND_GUID_PREFIXES``.

Existing rows are backfilled in id order within each kind, so the numbering is
stable and reproducible rather than dependent on row iteration order.

This migration is idempotent and backend-agnostic: it adds what is missing in
the configured backend (SQLite locally, PostgreSQL in production) and leaves
alone anything already present.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_name_guids.py
    PYTHONPATH=src python src/storage/migrations/add_name_guids.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_name_guids.py --dry-run
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.name_entity import name_kind_guid_prefix
from storage.models.name_entity import Name


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)


def add_guid_column(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Add the ``guid`` column and its unique index if missing.

    Returns:
        True if the column was added (or would be), False if it already existed
        or the table does not exist.
    """
    table_name = Name.__tablename__
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            print(f"Table '{table_name}' does not exist; run add_names.py first.")
            return False

        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "guid" in columns:
            print(f"Column '{table_name}.guid' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would add column '{table_name}.guid' (VARCHAR, nullable) + unique index.")
            return True

        print(f"Adding column '{table_name}.guid'...")
        session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN guid VARCHAR"))
        session.execute(
            text(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{table_name}_guid ON {table_name} (guid)")
        )
        session.commit()
        print("Column added successfully.")
        return True
    finally:
        session.close()


def backfill_guids(config: DataSourceConfig, *, dry_run: bool = False) -> int:
    """Assign a GUID to every name that lacks one.

    Numbering continues from the highest GUID already in each kind's namespace,
    so re-running after a partial backfill never reuses a number.

    Returns:
        The number of names given a GUID (or that would be).
    """
    session = create_session(config)
    try:
        names: List[Name] = session.query(Name).order_by(Name.id).all()

        next_sequence: Dict[str, int] = defaultdict(lambda: 1)
        for name in names:
            if not name.guid:
                continue
            prefix, _, sequence = name.guid.rpartition("_")
            if sequence.isdigit():
                next_sequence[prefix] = max(next_sequence[prefix], int(sequence) + 1)

        assigned = 0
        for name in names:
            if name.guid:
                continue
            try:
                prefix = name_kind_guid_prefix(name.kind)
            except ValueError as unknown_kind:
                print(f"Skipping name {name.id} ({name.name_text!r}): {unknown_kind}")
                continue
            guid = f"{prefix}_{next_sequence[prefix]:03d}"
            next_sequence[prefix] += 1
            assigned += 1
            if dry_run:
                print(f"Would assign {guid} to {name.name_text!r} ({name.kind}).")
            else:
                name.guid = guid

        if assigned and not dry_run:
            session.commit()
            print(f"Assigned GUIDs to {assigned} name(s).")
        elif not assigned:
            print("Every name already has a GUID; nothing to backfill.")
        return assigned
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Add and backfill names.guid")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--db-path",
        default=WORDFREQ_DB_PATH,
        help=f"Path to SQLite database (default: {WORDFREQ_DB_PATH})",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL instead of SQLite",
    )
    args = parser.parse_args()

    config = build_data_source_config(args.db_path, args.postgres)
    database_label = config.postgres_url if args.postgres else config.sqlite_path

    print(f"Database: {database_label}")
    print(f"Backend: {config.backend_type.value}")
    print(f"Dry run: {args.dry_run}")
    print()

    add_guid_column(config, dry_run=args.dry_run)
    backfill_guids(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
