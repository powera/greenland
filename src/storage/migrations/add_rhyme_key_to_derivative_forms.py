#!/usr/bin/env python3
"""
Migration: Add rhyme_key column to derivative_forms table.

The rhyme_key column stores a phonetic rhyme family identifier derived from
the IPA pronunciation.  For example, all words whose IPA ends in the same
stressed-vowel-through-coda pattern receive the same key (e.g. "æt" for
cat, bat, hat).

This column is nullable — derivative forms without an IPA pronunciation
(or whose IPA cannot be parsed) will have NULL.
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


def add_rhyme_key_column(session: Session) -> bool:
    """Add rhyme_key column to derivative_forms table if it doesn't exist."""
    if check_column_exists(session, "derivative_forms", "rhyme_key"):
        print("Column 'rhyme_key' already exists in derivative_forms table")
        return False

    print("Adding 'rhyme_key' column to derivative_forms table...")
    session.execute(text("ALTER TABLE derivative_forms ADD COLUMN rhyme_key VARCHAR"))
    session.commit()
    print("Column added successfully")

    print("Creating composite index on (language_code, rhyme_key)...")
    session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_derivative_forms_lang_rhyme "
            "ON derivative_forms (language_code, rhyme_key)"
        )
    )
    session.commit()
    print("Index created successfully")

    return True


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add rhyme_key column to derivative_forms")
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
            if check_column_exists(session, "derivative_forms", "rhyme_key"):
                print("Column 'rhyme_key' already exists — nothing to do")
            else:
                print("Would add 'rhyme_key' column to derivative_forms table")
                print("Would create index ix_derivative_forms_lang_rhyme")
        else:
            add_rhyme_key_column(session)

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
