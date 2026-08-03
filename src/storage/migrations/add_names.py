#!/usr/bin/env python3
"""
Migration: Create the ``names`` / ``name_translations`` tables and add
``sentence_words.name_id``.

Names are proper names used in our texts (dialog speakers, invented shops and
streets) that are neither lemmas nor concepts -- see
``storage/models/name_entity.py`` for why they need their own table and their
own per-language renderings. ``sentence_words`` gains a nullable ``name_id`` so
a token like "George" resolves to a name instead of being left unresolved and
counted as a vocabulary gap.

This migration is idempotent and backend-agnostic: it creates whatever is
missing in the configured backend (SQLite locally, PostgreSQL in production)
and does nothing for parts that already exist.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_names.py
    PYTHONPATH=src python src/storage/migrations/add_names.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_names.py --dry-run
"""

import argparse
import sys
from pathlib import Path
from typing import cast

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Table, inspect, text

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.name_entity import Name, NameTranslation
from storage.models.schema import SentenceWord


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


def create_name_tables(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Create the names and name_translations tables if they do not exist.

    Args:
        config: Storage configuration selecting the backend.
        dry_run: If True, report what would happen without creating anything.

    Returns:
        True if at least one table was created (or would be), else False.
    """
    session = create_session(config)
    created_any = False
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        for model in (Name, NameTranslation):
            table_name = model.__tablename__
            if inspector.has_table(table_name):
                print(f"Table '{table_name}' already exists; nothing to do.")
                continue
            if dry_run:
                print(f"Would create table '{table_name}'.")
                created_any = True
                continue
            print(f"Creating table '{table_name}'...")
            cast(Table, model.__table__).create(bind, checkfirst=True)
            created_any = True
        return created_any
    finally:
        session.close()


def add_sentence_word_name_id(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Add the ``name_id`` column to sentence_words if missing.

    Args:
        config: Storage configuration selecting the backend.
        dry_run: If True, report what would happen without altering the table.

    Returns:
        True if the column was added (or would be), False if it already existed
        or the table does not exist.
    """
    table_name = SentenceWord.__tablename__
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            print(f"Table '{table_name}' does not exist; nothing to do.")
            return False

        columns = {col["name"] for col in inspector.get_columns(table_name)}
        if "name_id" in columns:
            print(f"Column '{table_name}.name_id' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would add column '{table_name}.name_id' (INTEGER, nullable) + index.")
            return True

        print(f"Adding column '{table_name}.name_id'...")
        session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN name_id INTEGER"))
        session.execute(
            text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_name_id ON {table_name} (name_id)")
        )
        session.commit()
        print("Column added successfully.")
        return True
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(
        description="Create names/name_translations and add sentence_words.name_id"
    )
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

    create_name_tables(config, dry_run=args.dry_run)
    add_sentence_word_name_id(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
