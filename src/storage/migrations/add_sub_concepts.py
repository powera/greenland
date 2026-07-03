#!/usr/bin/env python3
"""
Migration: Create the ``sub_concepts`` table and extend ``concept_wikidata_index``.

Sub-concepts are sub-encyclopedia entries (e.g. individual chess openings, one
team's season, one bird species): tracked topics deliberately kept out of the
main encyclopedia. They share the Wikidata reverse index with main concepts, so
``concept_wikidata_index`` gains a nullable ``sub_concept_id`` column (mutually
exclusive with ``concept_id``; the CHECK constraint applies to fresh databases
via the model, while existing databases rely on the CRUD-layer guard).

This migration is idempotent and backend-agnostic: it creates the table /
column in whichever backend is configured (SQLite locally, PostgreSQL in
production) and does nothing for parts that already exist.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_sub_concepts.py
    PYTHONPATH=src python src/storage/migrations/add_sub_concepts.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_sub_concepts.py --dry-run
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
from storage.models.concept import ConceptWikidataIndex, SubConcept


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


def create_sub_concepts_table(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Create the sub_concepts table if it does not already exist.

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
        if inspector.has_table(SubConcept.__tablename__):
            print(f"Table '{SubConcept.__tablename__}' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would create table '{SubConcept.__tablename__}'.")
            return True

        print(f"Creating table '{SubConcept.__tablename__}'...")
        cast(Table, SubConcept.__table__).create(bind, checkfirst=True)
        print("Table created successfully.")
        return True
    finally:
        session.close()


def add_sub_concept_id_column(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Add the ``sub_concept_id`` column to concept_wikidata_index if missing.

    Args:
        config: Storage configuration selecting the backend.
        dry_run: If True, report what would happen without altering the table.

    Returns:
        True if the column was added (or would be), False if it already existed
        or the table does not exist.
    """
    table_name = ConceptWikidataIndex.__tablename__
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            print(f"Table '{table_name}' does not exist; nothing to do.")
            return False

        columns = {col["name"] for col in inspector.get_columns(table_name)}
        if "sub_concept_id" in columns:
            print(f"Column '{table_name}.sub_concept_id' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would add column '{table_name}.sub_concept_id' (INTEGER, nullable) + index.")
            return True

        print(f"Adding column '{table_name}.sub_concept_id'...")
        session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN sub_concept_id INTEGER"))
        session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_sub_concept_id "
                f"ON {table_name} (sub_concept_id)"
            )
        )
        session.commit()
        print("Column added successfully.")
        return True
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(
        description="Create sub_concepts and add concept_wikidata_index.sub_concept_id"
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

    create_sub_concepts_table(config, dry_run=args.dry_run)
    add_sub_concept_id_column(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
