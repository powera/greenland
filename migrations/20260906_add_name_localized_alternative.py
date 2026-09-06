#!/usr/bin/env python3
"""
Migration: Add ``name_translations.localized_alternative``.

A name has one rendering per language, and that is the one a translation uses:
Lithuanian needs a declinable ``Džonas``, Chinese needs ``约翰``, and the
sentence pipeline pins them so the same character is not spelled two ways in
consecutive sentences.

Some languages also have a *localized* alternative -- Russian would write
``Иван`` for John if the cast were recast as Russian rather than respelled.
That is not a competing rendering and is never sent to a model; it is recorded
so a reviewer reading Russian output can tell a deliberate localization from a
botched transliteration. One nullable column holds it, with the existing
free-form ``notes`` carrying any explanation.

The column is nullable with no default, so this is a plain ``ADD COLUMN`` on
both backends -- no table rebuild, no unique-key change, and every existing row
reads back unchanged with the field empty.

Idempotent: the column is added only when absent, so a re-run is a no-op.

Usage:
    PYTHONPATH=src python migrations/20260906_add_name_localized_alternative.py
    PYTHONPATH=src python migrations/20260906_add_name_localized_alternative.py --postgres
    PYTHONPATH=src python migrations/20260906_add_name_localized_alternative.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig

_TABLE_NAME = "name_translations"
_COLUMN_NAME = "localized_alternative"


def _bind(session: Session) -> Connection | Engine:
    """The session's bind, which the DDL below needs."""
    bind = session.get_bind()
    if bind is None:  # pragma: no cover - a sessionmaker always binds
        raise RuntimeError("Session has no bind; cannot run DDL.")
    return bind


def column_exists(session: Session) -> bool:
    """Whether the column is already present."""
    columns = inspect(_bind(session)).get_columns(_TABLE_NAME)
    return any(column["name"] == _COLUMN_NAME for column in columns)


def add_column(session: Session) -> bool:
    """Add the column if absent. Returns True if it was added.

    ``VARCHAR`` with no length is what the model's ``String`` maps to on both
    SQLite and PostgreSQL, so the added column matches a freshly created table.
    """
    if column_exists(session):
        print(f"Column {_TABLE_NAME}.{_COLUMN_NAME} already exists; leaving it alone.")
        return False

    session.execute(text(f"ALTER TABLE {_TABLE_NAME} ADD COLUMN {_COLUMN_NAME} VARCHAR"))
    session.commit()
    print(f"Added column {_TABLE_NAME}.{_COLUMN_NAME}.")
    return True


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


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(
        description="Add name_translations.localized_alternative",
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

    session = create_session(config)
    try:
        if args.dry_run:
            if column_exists(session):
                print(f"Column {_TABLE_NAME}.{_COLUMN_NAME} exists; nothing to do.")
            else:
                print(f"Would add column {_TABLE_NAME}.{_COLUMN_NAME} (VARCHAR, nullable).")
            print("\n** DRY RUN - No changes were made **")
        else:
            add_column(session)
            print("\nMigration complete.")
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
