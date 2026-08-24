#!/usr/bin/env python3
"""
Migration: Add ``name_translations.rendering_kind`` and widen the unique key.

A rendering answers one of two different questions. Lithuanian ``Džonas`` and
Chinese ``约翰`` respell the same character for a script that cannot hold the
original -- that is forced. Russian ``Иван`` and Spanish ``Juan`` recast the
character as a local one -- that is an editorial choice, and both it and the
plain transliteration ``Джон`` are correct for different texts.

Storing only one string per language could not express that, and left a
reviewer unable to tell a deliberate ``Иван`` from a botched transliteration.
This migration adds the discriminator and widens ``uq_name_translation`` from
(name_id, language_code) to (name_id, language_code, rendering_kind) so a
language can hold one rendering of each kind.

Every existing row becomes a ``transliteration``, which is what it already
meant.

Widening the key differs by backend. PostgreSQL can drop the old constraint and
create the wider one in place. SQLite cannot: the original key was declared
inside ``CREATE TABLE`` as a table constraint, which ``DROP INDEX`` silently
fails to remove -- it reports success while the constraint keeps rejecting the
second rendering. There the table is rebuilt from the model instead, copying
every row across, and the resulting DDL is checked afterwards so a silent no-op
cannot pass for a migration.

This migration is idempotent and backend-agnostic: it adds what is missing in
the configured backend (SQLite locally, PostgreSQL in production) and leaves
alone anything already present.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_name_rendering_kind.py
    PYTHONPATH=src python src/storage/migrations/add_name_rendering_kind.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_name_rendering_kind.py --dry-run
"""

import argparse
import sys
from pathlib import Path
from typing import Any, List, cast

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Table, inspect, text

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.name_entity import DEFAULT_RENDERING_KIND, NameTranslation

CONSTRAINT_NAME = "uq_name_translation"


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)


def add_rendering_kind_column(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Add the ``rendering_kind`` column if missing.

    The column is NOT NULL with a ``transliteration`` default, so existing rows
    are backfilled by the DEFAULT rather than by a separate UPDATE pass.

    Returns:
        True if the column was added (or would be), False if it already existed
        or the table does not exist.
    """
    table_name = NameTranslation.__tablename__
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            print(f"Table '{table_name}' does not exist; run add_names.py first.")
            return False

        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "rendering_kind" in columns:
            print(f"Column '{table_name}.rendering_kind' already exists; nothing to do.")
            return False

        if dry_run:
            print(
                f"Would add column '{table_name}.rendering_kind' "
                f"(VARCHAR NOT NULL DEFAULT '{DEFAULT_RENDERING_KIND}') + index."
            )
            return True

        print(f"Adding column '{table_name}.rendering_kind'...")
        session.execute(
            text(
                f"ALTER TABLE {table_name} ADD COLUMN rendering_kind VARCHAR "
                f"NOT NULL DEFAULT '{DEFAULT_RENDERING_KIND}'"
            )
        )
        session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_rendering_kind "
                f"ON {table_name} (rendering_kind)"
            )
        )
        session.commit()
        print("Column added successfully.")
        return True
    finally:
        session.close()


def widen_unique_constraint(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Rebuild ``uq_name_translation`` to include ``rendering_kind``.

    On SQLite the rebuild runs again on a re-run rather than short-circuiting:
    the widened key lands as an inline table constraint, which does not surface
    as a named index for the check below. The rebuild is data-preserving and
    verified afterwards, so repeating it is safe.

    Returns:
        True if the constraint was rebuilt (or would be), False if it was
        already correct or the table does not exist.
    """
    table_name = NameTranslation.__tablename__
    target_columns = ["name_id", "language_code", "rendering_kind"]

    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            print(f"Table '{table_name}' does not exist; nothing to widen.")
            return False

        existing_indexes = {index["name"]: index for index in inspector.get_indexes(table_name)}
        current = existing_indexes.get(CONSTRAINT_NAME)
        if current is not None and list(current.get("column_names") or []) == target_columns:
            print(f"Constraint '{CONSTRAINT_NAME}' already covers {target_columns}; nothing to do.")
            return False

        if dry_run:
            print(f"Would rebuild '{CONSTRAINT_NAME}' as a unique index over {target_columns}.")
            return True

        print(f"Rebuilding '{CONSTRAINT_NAME}' over {target_columns}...")
        if config.backend_type == BackendType.POSTGRES:
            # PostgreSQL can swap the key in place.
            session.execute(
                text(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}")
            )
            session.execute(text(f"DROP INDEX IF EXISTS {CONSTRAINT_NAME}"))
            session.execute(
                text(
                    f"CREATE UNIQUE INDEX {CONSTRAINT_NAME} "
                    f"ON {table_name} ({', '.join(target_columns)})"
                )
            )
        else:
            _rebuild_sqlite_table(session, table_name, target_columns)
        session.commit()

        _assert_constraint_widened(session, table_name)
        print("Constraint rebuilt successfully.")
        return True
    finally:
        session.close()


def _rebuild_sqlite_table(session: Any, table_name: str, target_columns: List[str]) -> None:
    """Recreate a SQLite table to widen its inline UNIQUE table constraint.

    The original key was declared inside ``CREATE TABLE`` as
    ``CONSTRAINT uq_name_translation UNIQUE (name_id, language_code)``. SQLite
    has no ``ALTER TABLE ... DROP CONSTRAINT``, and ``DROP INDEX`` does not
    touch a table constraint -- it silently succeeds while the constraint keeps
    rejecting the second rendering. The only way out is to rebuild the table.
    """
    inspector = inspect(session.get_bind())
    columns = [column["name"] for column in inspector.get_columns(table_name)]
    column_list = ", ".join(columns)
    # A rename carries the old table's indexes with it, so recreating from the
    # model would collide on every index name. Drop them first.
    index_names = [
        index["name"] for index in inspector.get_indexes(table_name) if index.get("name")
    ]

    session.execute(text("PRAGMA foreign_keys=OFF"))
    for index_name in index_names:
        session.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
    session.execute(text(f"ALTER TABLE {table_name} RENAME TO {table_name}_old"))

    # Recreate from the model, which already carries the widened constraint.
    # cast because the declarative __table__ is typed as the looser FromClause.
    cast(Table, NameTranslation.__table__).create(bind=session.get_bind())

    session.execute(
        text(f"INSERT INTO {table_name} ({column_list}) SELECT {column_list} FROM {table_name}_old")
    )
    session.execute(text(f"DROP TABLE {table_name}_old"))
    session.execute(text("PRAGMA foreign_keys=ON"))


def _assert_constraint_widened(session: Any, table_name: str) -> None:
    """Fail loudly if the old two-column key still rejects a second rendering.

    A silent no-op here is the whole failure mode this migration exists to
    avoid: ``DROP INDEX`` reports success against an inline table constraint
    while leaving it in force, so the feature would look migrated and still not
    work. Checking the resulting DDL is cheap and unambiguous.
    """
    definition = session.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).scalar()
    if definition is None:
        return
    normalized = " ".join(str(definition).split())
    if "UNIQUE (name_id, language_code)" in normalized:
        raise RuntimeError(
            f"{table_name} still carries the two-column unique constraint; "
            "a language cannot hold both a transliteration and a localization."
        )


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(
        description="Add name_translations.rendering_kind and widen its unique key"
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

    add_rendering_kind_column(config, dry_run=args.dry_run)
    widen_unique_constraint(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
