#!/usr/bin/env python3
"""
Migration: Add example_sentence column to pending_imports table.

This migration adds an example_sentence column so that the word's source
sentence can be stored alongside the pending import, giving the LLM better
context when determining the correct sense during staging and approval.
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
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_example_sentence_column(session: Session, dry_run: bool = False) -> bool:
    if check_column_exists(session, "pending_imports", "example_sentence"):
        print("Column 'example_sentence' already exists in pending_imports table")
        return False

    if dry_run:
        print("Would add 'example_sentence' column to pending_imports table")
        return True

    print("Adding 'example_sentence' column to pending_imports table...")
    session.execute(text("ALTER TABLE pending_imports ADD COLUMN example_sentence TEXT"))
    session.commit()
    print("Column added successfully")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Add example_sentence to pending_imports")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    session = create_database_session(args.db_path)

    try:
        column_added = add_example_sentence_column(session, dry_run=args.dry_run)
        if args.dry_run:
            print("\n** DRY RUN - No changes were made **")
        elif column_added:
            print("\n** Migration complete **")
        else:
            print("\n** No changes needed **")
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
