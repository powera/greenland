#!/usr/bin/env python3
"""Migration: add translation status metadata to lemma_translations.

The fields mark useful learner cues that are not ordinary historical/native
vocabulary, such as Neo-Latin terms, modern loanwords, or descriptive
coinages.
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
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_column_if_missing(
    session: Session, column_name: str, column_type: str, dry_run: bool = False
) -> bool:
    """Add a column to lemma_translations if it does not already exist."""
    if check_column_exists(session, "lemma_translations", column_name):
        print(f"Column '{column_name}' already exists in lemma_translations")
        return False

    if dry_run:
        print(f"Would add '{column_name}' column to lemma_translations")
        return True

    print(f"Adding '{column_name}' column to lemma_translations...")
    session.execute(text(f"ALTER TABLE lemma_translations ADD COLUMN {column_name} {column_type}"))
    return True


def add_translation_status_columns(session: Session, dry_run: bool = False) -> bool:
    """Add translation_status and translation_status_note columns."""
    changed = False
    changed |= add_column_if_missing(session, "translation_status", "VARCHAR", dry_run=dry_run)
    changed |= add_column_if_missing(session, "translation_status_note", "TEXT", dry_run=dry_run)
    if changed and not dry_run:
        session.commit()
        print("Columns added successfully")
    return changed


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Add translation status metadata to lemma_translations"
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
        columns_added = add_translation_status_columns(session, dry_run=args.dry_run)
        if args.dry_run:
            print("\n** DRY RUN - No changes were made **")
        elif columns_added:
            print("\n** Migration complete **")
        else:
            print("\n** No changes needed **")
    except Exception as error:
        print(f"\nError during migration: {error}")
        import traceback

        traceback.print_exc()
        session.rollback()
        return 1
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
