#!/usr/bin/env python3
"""
Migration: Add a tags column to pending_imports.

Carries free-form tags from the staging row to the lemma it eventually becomes,
so a corpus ingested with ``genys --tags legal`` produces lemmas tagged
``legal`` without a second pass. The column mirrors ``Lemma.tags``: a JSON array
of strings, NULL when there are no tags.

Nullable and not backfilled -- imports staged before this existed keep NULL.
"""

import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.database import create_database_session

_TABLE_NAME = "pending_imports"
_COLUMN_NAME = "tags"
_COLUMN_TYPE = "TEXT"


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_tags_column(session: Session) -> bool:
    """Add the tags column to pending_imports if it does not exist.

    Returns True when the column was added.
    """
    if check_column_exists(session, _TABLE_NAME, _COLUMN_NAME):
        print(f"Column {_TABLE_NAME}.{_COLUMN_NAME} already exists; nothing to do.")
        return False

    session.execute(text(f"ALTER TABLE {_TABLE_NAME} ADD COLUMN {_COLUMN_NAME} {_COLUMN_TYPE}"))
    session.commit()
    print(f"Added column {_TABLE_NAME}.{_COLUMN_NAME} ({_COLUMN_TYPE}).")
    return True


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add a tags column to pending_imports")
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
            if check_column_exists(session, _TABLE_NAME, _COLUMN_NAME):
                print(f"Column '{_COLUMN_NAME}' already exists - nothing to do")
            else:
                print(f"Would add '{_COLUMN_NAME}' column to {_TABLE_NAME} table")
            print("\n** DRY RUN - No changes were made **")
        else:
            add_tags_column(session)
            print("\n** Migration complete **")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
