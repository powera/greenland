#!/usr/bin/env python3
"""Drop the ``text_works`` and ``text_versions`` tables.

The story library (full texts of fables, poems, songs and conversations) was
removed as out of scope; its models, CRUD, Barsukas pages and the ozys agent
are gone, so nothing reads or writes these tables any more.

Preview by default; --apply drops them. A table that still holds rows stops
the migration instead of being dropped, so stored text is never discarded
silently. On SQLite --apply first takes a major backup (dropping a table is
irreversible). Safe to rerun: a missing table is skipped.
"""

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from typing import List

from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.backup import create_backup

# Child first: text_versions holds the foreign key to text_works.
_TABLES: tuple[str, ...] = ("text_versions", "text_works")


def _bind(session: Session) -> Connection | Engine:
    """The session's bind, which DDL needs."""
    bind = session.get_bind()
    if bind is None:  # pragma: no cover - a sessionmaker always binds
        raise RuntimeError("Session has no bind; cannot run DDL.")
    return bind


def present_tables(session: Session) -> List[str]:
    """The text-work tables that still exist, in drop order."""
    existing = set(inspect(_bind(session)).get_table_names())
    return [table for table in _TABLES if table in existing]


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Drop the tables")
    parser.add_argument(
        "--db-path",
        default=WORDFREQ_DB_PATH,
        help=f"Path to SQLite database (default: {WORDFREQ_DB_PATH})",
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use the PostgreSQL (concepts) database instead of SQLite",
    )
    args = parser.parse_args()

    config = build_data_source_config(args.db_path, args.postgres)
    print(f"Backend: {config.backend_type.value}")

    session = create_session(config)
    try:
        tables = present_tables(session)
        if not tables:
            print("No text-work tables present; nothing to do.")
            return 0
        nonempty = []
        for table in tables:
            count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            print(f"{table}: {count} row(s)")
            if count:
                nonempty.append(table)
        if nonempty:
            print(f"Refusing to drop non-empty table(s): {', '.join(nonempty)}")
            return 1
        if not args.apply:
            print(f"Would drop: {', '.join(tables)} (preview; pass --apply)")
            return 0
        if not args.postgres:
            print(f"Major backup: {create_backup(config, 'drop-text-works', 'major')}")
        for table in tables:
            session.execute(text(f"DROP TABLE {table}"))
        session.commit()
        print(f"Dropped: {', '.join(tables)}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
