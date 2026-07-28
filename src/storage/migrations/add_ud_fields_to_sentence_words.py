#!/usr/bin/env python3
"""
Migration: Add ud_relation and ud_head_position columns to sentence_words.

These carry the Universal Dependencies annotation produced by the Phase-4
dependency pass: a core UD relation label (nsubj, obj, det, ...) and the
zero-based position of the word's head, with -1 marking the sentence root.

Both columns are nullable — existing sentences are not backfilled, so every
word decomposed before Phase 4 existed keeps NULL for both.
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

_TABLE_NAME = "sentence_words"
_COLUMN_TYPES = {
    "ud_relation": "VARCHAR",
    "ud_head_position": "INTEGER",
}


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_ud_columns(session: Session) -> bool:
    """Add the UD columns to sentence_words if they don't exist.

    Returns True when at least one column was added.
    """
    added_any = False
    for column_name, column_type in _COLUMN_TYPES.items():
        if check_column_exists(session, _TABLE_NAME, column_name):
            print(f"Column '{column_name}' already exists in {_TABLE_NAME} table")
            continue

        print(f"Adding '{column_name}' column to {_TABLE_NAME} table...")
        session.execute(text(f"ALTER TABLE {_TABLE_NAME} ADD COLUMN {column_name} {column_type}"))
        session.commit()
        print("Column added successfully")
        added_any = True

    return added_any


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Add ud_relation and ud_head_position columns to sentence_words"
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
            for column_name in _COLUMN_TYPES:
                if check_column_exists(session, _TABLE_NAME, column_name):
                    print(f"Column '{column_name}' already exists — nothing to do")
                else:
                    print(f"Would add '{column_name}' column to {_TABLE_NAME} table")
        else:
            add_ud_columns(session)

        if args.dry_run:
            print("\n** DRY RUN - No changes were made **")
        else:
            print("\n** Migration complete **")

    except Exception as e:
        print(f"\nError during migration: {e}")
        import traceback

        traceback.print_exc()
        session.rollback()
        return 1
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
