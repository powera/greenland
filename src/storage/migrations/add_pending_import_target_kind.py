#!/usr/bin/env python3
"""
Migration: Add target_kind, name_kind, and concept_type to pending_imports.

A staged term becomes one of three things -- a lemma, a name, or a concept --
and until these columns existed every row was implicitly a lemma, so "George"
and "World War II" were queued up to become vocabulary.

``target_kind`` is NOT NULL with a default of "lemma", which is exactly the old
behavior, so existing rows need no backfill beyond that default. ``name_kind``
and ``concept_type`` are nullable and only meaningful for their own kind.
"""

import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from typing import List, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.database import create_database_session

_TABLE_NAME = "pending_imports"

# (column, type, extra DDL). target_kind carries a server default so existing
# rows get "lemma" without a separate UPDATE.
_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("target_kind", "TEXT", "NOT NULL DEFAULT 'lemma'"),
    ("name_kind", "TEXT", ""),
    ("concept_type", "TEXT", ""),
)


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def missing_columns(session: Session) -> List[str]:
    """Names of the columns this migration would add."""
    return [
        column_name
        for column_name, _type, _extra in _COLUMNS
        if not check_column_exists(session, _TABLE_NAME, column_name)
    ]


def add_target_kind_columns(session: Session) -> List[str]:
    """Add the missing columns. Returns the names of the ones added."""
    added: List[str] = []
    for column_name, column_type, extra in _COLUMNS:
        if check_column_exists(session, _TABLE_NAME, column_name):
            print(f"Column {_TABLE_NAME}.{column_name} already exists; nothing to do.")
            continue
        clause = f"ALTER TABLE {_TABLE_NAME} ADD COLUMN {column_name} {column_type} {extra}".strip()
        session.execute(text(clause))
        added.append(column_name)
        print(f"Added column {_TABLE_NAME}.{column_name} ({column_type}).")
    if added:
        session.commit()
    return added


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Add target_kind/name_kind/concept_type columns to pending_imports"
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

    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    print(f"Dry run: {args.dry_run}")
    print()

    session = create_database_session(args.db_path)
    try:
        if args.dry_run:
            pending_columns = missing_columns(session)
            if pending_columns:
                print(f"Would add to {_TABLE_NAME}: {', '.join(pending_columns)}")
            else:
                print("All columns already exist - nothing to do")
            print("\n** DRY RUN - No changes were made **")
        else:
            add_target_kind_columns(session)
            print("\n** Migration complete **")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
