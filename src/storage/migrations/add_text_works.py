#!/usr/bin/env python3
"""
Migration: Create the ``text_works`` and ``text_versions`` tables.

Text works are the story library beside the concepts encyclopedia: a work row
(fable, folk tale, conversation, poem, song, ...) anchors one or more version
rows carrying the actual text (per language x difficulty; English-only for
now). See docs/fables_design.md.

This migration is idempotent and backend-agnostic: it creates the tables in
whichever backend is configured (SQLite locally, PostgreSQL in production) and
does nothing for tables that already exist. No index changes to existing
tables and no backfill are required -- populating the library is curation, not
migration.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_text_works.py
    PYTHONPATH=src python src/storage/migrations/add_text_works.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_text_works.py --dry-run
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
from storage.models.text_work import TextVersion, TextWork


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


def create_table_if_missing(
    config: DataSourceConfig, model: type, *, dry_run: bool = False
) -> bool:
    """Create a model's table if it does not already exist.

    Args:
        config: Storage configuration selecting the backend.
        model: The declarative model whose table to create.
        dry_run: If True, report what would happen without creating the table.

    Returns:
        True if the table was created (or would be), False if it already existed.
    """
    table_name = cast(str, model.__tablename__)  # type: ignore[attr-defined]
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if inspector.has_table(table_name):
            print(f"Table '{table_name}' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would create table '{table_name}'.")
            return True

        print(f"Creating table '{table_name}'...")
        cast(Table, model.__table__).create(bind, checkfirst=True)  # type: ignore[attr-defined]
        print("Table created successfully.")
        return True
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Create the text_works and text_versions tables")
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

    # Works first: text_versions carries the foreign key.
    create_table_if_missing(config, TextWork, dry_run=args.dry_run)
    create_table_if_missing(config, TextVersion, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
