#!/usr/bin/env python3
"""
Migration: Add pending_import_id to SentencePatternWord and make lemma_id nullable.

This migration:
1. Adds pending_import_id column to sentence_pattern_words table
2. Makes lemma_id nullable (was NOT NULL before)

SQLite doesn't support ALTER COLUMN, so we recreate the table.

This enables tracking words used in sentences that don't yet exist in the
lemmas table, by linking to pending_imports instead.
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
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def check_column_nullable(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column is nullable."""
    inspector = inspect(session.bind)
    for col in inspector.get_columns(table_name):
        if col["name"] == column_name:
            return bool(col["nullable"])
    return False


def migrate_table(session: Session, dry_run: bool = False) -> bool:
    """Recreate sentence_pattern_words table with pending_import_id and nullable lemma_id."""
    has_column = check_column_exists(session, "sentence_pattern_words", "pending_import_id")
    lemma_nullable = check_column_nullable(session, "sentence_pattern_words", "lemma_id")

    if has_column and lemma_nullable:
        print("Table already has pending_import_id and lemma_id is nullable")
        return False

    if dry_run:
        print("Would recreate sentence_pattern_words table with:")
        print("  - pending_import_id column (nullable)")
        print("  - lemma_id column (nullable)")
        return True

    print("Recreating sentence_pattern_words table...")

    # SQLite table recreation approach
    session.execute(text("PRAGMA foreign_keys=OFF"))

    # Create new table with correct schema
    session.execute(text("""
        CREATE TABLE sentence_pattern_words_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sentence_id INTEGER NOT NULL REFERENCES sentences(id),
            lemma_id INTEGER REFERENCES lemmas(id),
            pending_import_id INTEGER REFERENCES pending_imports(id),
            position INTEGER NOT NULL,
            slot_name VARCHAR NOT NULL,
            english_text VARCHAR NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (sentence_id, position)
        )
    """))

    # Copy data from old table
    session.execute(text("""
        INSERT INTO sentence_pattern_words_new
            (id, sentence_id, lemma_id, pending_import_id, position, slot_name, english_text, added_at)
        SELECT id, sentence_id, lemma_id, NULL, position, slot_name, english_text, added_at
        FROM sentence_pattern_words
    """))

    # Drop old table and rename new one
    session.execute(text("DROP TABLE sentence_pattern_words"))
    session.execute(text("ALTER TABLE sentence_pattern_words_new RENAME TO sentence_pattern_words"))

    session.execute(text("PRAGMA foreign_keys=ON"))
    session.commit()

    print("Table recreated successfully")
    return True


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add pending_import_id to sentence_pattern_words")
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
        migrate_table(session, dry_run=args.dry_run)

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
