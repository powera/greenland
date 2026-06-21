#!/usr/bin/env python3
"""
Migration: Add a ``title`` column to ``concept_wikidata_index``.

The Wikidata reverse index originally tracked only ``qid -> concept_id``. We now
also cache the remote Wikipedia article title for Q-ids that have no concept yet
(e.g. ranked "wanted" red links resolved from titles). This migration adds a
nullable ``title`` column. It is idempotent and backend-agnostic.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_concept_wikidata_index_title.py
    PYTHONPATH=src python src/storage/migrations/add_concept_wikidata_index_title.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_concept_wikidata_index_title.py --dry-run
"""

import argparse
import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.concept import ConceptWikidataIndex


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


def add_title_column(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Add the ``title`` column to concept_wikidata_index if it is missing.

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
        if "title" in columns:
            print(f"Column '{table_name}.title' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would add column '{table_name}.title' (VARCHAR, nullable).")
            return True

        print(f"Adding column '{table_name}.title'...")
        session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN title VARCHAR"))
        session.commit()
        print("Column added successfully.")
        return True
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Add a title column to concept_wikidata_index")
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

    add_title_column(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
