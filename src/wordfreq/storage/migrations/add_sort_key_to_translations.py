#!/usr/bin/env python3
"""
Migration: Add sort_key column to lemma_translations table.

The sort_key column stores a romanized/phonetic form of the translation
for languages where the native script doesn't sort in a useful Latin order:
  - Chinese (zh): pinyin, e.g. "chī" for 吃
  - Japanese (ja): hiragana reading, e.g. "たべる" for 食べる
  - Korean (ko): already alphabetic (Hangul), but stored for consistency

This column is nullable and not load-bearing — it is used only for
dictionary browse ordering and alphabet-bar filtering.
"""

import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from wordfreq.storage.database import create_database_session


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]  # type: ignore[union-attr]
    return column_name in columns


def add_sort_key_column(session: Session) -> bool:
    """Add sort_key column to lemma_translations table if it doesn't exist."""
    if check_column_exists(session, "lemma_translations", "sort_key"):
        print("Column 'sort_key' already exists in lemma_translations table")
        return False

    print("Adding 'sort_key' column to lemma_translations table...")
    session.execute(text("ALTER TABLE lemma_translations ADD COLUMN sort_key VARCHAR"))
    session.commit()
    print("Column added successfully")

    print("Creating index on sort_key...")
    session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_lemma_translations_sort_key "
            "ON lemma_translations (sort_key)"
        )
    )
    session.commit()
    print("Index created successfully")

    return True


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add sort_key column to lemma_translations")
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
            if check_column_exists(session, "lemma_translations", "sort_key"):
                print("Column 'sort_key' already exists — nothing to do")
            else:
                print("Would add 'sort_key' column to lemma_translations table")
                print("Would create index ix_lemma_translations_sort_key")
        else:
            add_sort_key_column(session)

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
