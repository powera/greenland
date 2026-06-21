#!/usr/bin/env python3
"""
Migration: Create the ``concepts`` table.

Concepts are encyclopedia-style entries (e.g. "World War II", "Art Deco") that
live outside the lemma/GUID/data-release machinery. This migration is idempotent
and backend-agnostic: it creates the table in whichever backend is configured
(SQLite locally, PostgreSQL in production) and does nothing if it already exists.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_concepts_table.py
    PYTHONPATH=src python src/storage/migrations/add_concepts_table.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_concepts_table.py --dry-run
"""

import argparse
import sys
from pathlib import Path
from typing import cast

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Table, inspect

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.concept import Concept


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=db_path,
    )


def create_concepts_table(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Create the concepts table if it does not already exist.

    Args:
        config: Storage configuration selecting the backend.
        dry_run: If True, report what would happen without creating the table.

    Returns:
        True if the table was created (or would be), False if it already existed.
    """
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if inspector.has_table(Concept.__tablename__):
            print(f"Table '{Concept.__tablename__}' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would create table '{Concept.__tablename__}'.")
            return True

        print(f"Creating table '{Concept.__tablename__}'...")
        cast(Table, Concept.__table__).create(bind, checkfirst=True)
        print("Table created successfully.")
        return True
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Create the concepts table")
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

    create_concepts_table(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
