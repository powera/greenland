#!/usr/bin/env python3
"""
Migration: Add disambiguation column to LemmaTranslation table.

This migration adds a disambiguation column to lemma_translations, allowing
per-language disambiguation for translations that share the same word in
the target language. For example, Lithuanian "oda" can mean both "skin" and
"leather", so we store a Lithuanian disambiguator to display alongside.
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


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_disambiguation_column(session: Session, dry_run: bool = False) -> bool:
    """Add disambiguation column to lemma_translations table if it doesn't exist."""
    if check_column_exists(session, "lemma_translations", "disambiguation"):
        print("Column 'disambiguation' already exists in lemma_translations table")
        return False

    if dry_run:
        print("Would add 'disambiguation' column to lemma_translations table")
        return True

    print("Adding 'disambiguation' column to lemma_translations table...")
    session.execute(text("ALTER TABLE lemma_translations ADD COLUMN disambiguation VARCHAR"))
    session.commit()
    print("Column added successfully")
    return True


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add disambiguation to LemmaTranslation")
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
        column_added = add_disambiguation_column(session, dry_run=args.dry_run)

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
