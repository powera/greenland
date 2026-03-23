#!/usr/bin/env python3
"""
Migration: add pronunciation columns to lemma_translations.

This migration adds:
1. ipa_pronunciation
2. phonetic_pronunciation
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.database import create_database_session


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Return True when the target column already exists."""
    inspector = inspect(session.bind)
    columns = [column["name"] for column in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_column_if_missing(session: Session, column_name: str) -> bool:
    """Add a pronunciation column when it does not already exist."""
    if check_column_exists(session, "lemma_translations", column_name):
        print(f"Column '{column_name}' already exists in lemma_translations")
        return False

    print(f"Adding '{column_name}' column to lemma_translations...")
    session.execute(text(f"ALTER TABLE lemma_translations ADD COLUMN {column_name} VARCHAR"))
    session.commit()
    print(f"Column '{column_name}' added successfully")
    return True


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add pronunciation columns to lemma_translations")
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
        for column_name in ("ipa_pronunciation", "phonetic_pronunciation"):
            if args.dry_run:
                if check_column_exists(session, "lemma_translations", column_name):
                    print(f"Column '{column_name}' already exists — nothing to do")
                else:
                    print(f"Would add '{column_name}' column to lemma_translations")
            else:
                add_column_if_missing(session, column_name)

        print(
            "\n** DRY RUN - No changes were made **"
            if args.dry_run
            else "\n** Migration complete **"
        )
        return 0
    except Exception as error:
        print(f"\nError during migration: {error}")
        import traceback

        traceback.print_exc()
        session.rollback()
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
