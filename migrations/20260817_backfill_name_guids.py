#!/usr/bin/env python3
"""
Migration: Backfill ``names.guid`` for existing names.

Names are now exported to ``data/release/names`` (their per-language renderings
- Džordžas, 乔治, ジョージ - are content that has to stay stable across every
text that uses a name), which means they need a release GUID like every other
exported element. The prefix encodes the name's kind; see
``storage.models.guid_prefixes.NAME_KIND_GUID_PREFIXES``.

Existing rows are backfilled in id order within each kind, so the numbering is
stable and reproducible rather than dependent on row iteration order.

Schema creation is handled by normal model initialization. This migration is
idempotent and backend-agnostic: it leaves existing GUIDs alone.

Usage:
    python migrations/20260817_backfill_name_guids.py
    python migrations/20260817_backfill_name_guids.py --postgres
    python migrations/20260817_backfill_name_guids.py --dry-run
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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
    parser = argparse.ArgumentParser(description="Backfill names.guid")
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

    backfill_guids(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
