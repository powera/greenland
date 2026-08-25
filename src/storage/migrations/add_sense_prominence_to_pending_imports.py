#!/usr/bin/env python3
"""
Migration: Add a sense_prominence column to pending_imports.

Carries the staging call's rating of how common a sense is onto the lemma it
eventually becomes. The pre-staged branch of ``approve_as_lemma`` makes no
second LLM call, so without this column the rating that the staging call
already paid for is discarded and every approved lemma lands on the schema
default ("common"), flattening the weighted frequency split in
``wordfreq.lexeme_frequency``.

Values are those of ``Lemma.sense_prominence`` (SENSE_PROMINENCE_VALUES).
Nullable and not backfilled -- imports staged before this existed keep NULL,
which means "unrated" and leaves the lemma at its default.
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
_COLUMN_NAME = "sense_prominence"
_COLUMN_TYPE = "VARCHAR"


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_sense_prominence_column(session: Session) -> bool:
    """Add the sense_prominence column to pending_imports if it does not exist.

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

    parser = argparse.ArgumentParser(description="Add a sense_prominence column to pending_imports")
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
            add_sense_prominence_column(session)
            print("\n** Migration complete **")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
