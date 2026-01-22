#!/usr/bin/env python3
"""
Migration: Add regional variant tables for pluricentric languages.

This migration creates:
1. lemma_regional_variants table - regional overrides for word translations
2. sentence_regional_variants table - regional overrides for sentence translations

These tables support pluricentric languages (en, es, pt, zh) where regional
variants may differ from the base translation.
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


def check_table_exists(session: Session, table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(session.bind)
    return table_name in inspector.get_table_names()


def create_lemma_regional_variants_table(session: Session, dry_run: bool = False) -> bool:
    """Create lemma_regional_variants table if it doesn't exist."""
    if check_table_exists(session, "lemma_regional_variants"):
        print("Table 'lemma_regional_variants' already exists")
        return False

    if dry_run:
        print("Would create 'lemma_regional_variants' table")
        return True

    print("Creating 'lemma_regional_variants' table...")
    session.execute(text("""
            CREATE TABLE lemma_regional_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
                region_code VARCHAR NOT NULL,
                translation VARCHAR NOT NULL,
                definition_text TEXT,
                verified BOOLEAN DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (lemma_id, region_code)
            )
            """))
    # Create index on region_code for efficient queries
    session.execute(
        text(
            "CREATE INDEX ix_lemma_regional_variants_region_code ON lemma_regional_variants(region_code)"
        )
    )
    # Create index on translation for search
    session.execute(
        text(
            "CREATE INDEX ix_lemma_regional_variants_translation ON lemma_regional_variants(translation)"
        )
    )
    session.commit()
    print("Table 'lemma_regional_variants' created successfully")
    return True


def create_sentence_regional_variants_table(session: Session, dry_run: bool = False) -> bool:
    """Create sentence_regional_variants table if it doesn't exist."""
    if check_table_exists(session, "sentence_regional_variants"):
        print("Table 'sentence_regional_variants' already exists")
        return False

    if dry_run:
        print("Would create 'sentence_regional_variants' table")
        return True

    print("Creating 'sentence_regional_variants' table...")
    session.execute(text("""
            CREATE TABLE sentence_regional_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sentence_id INTEGER NOT NULL REFERENCES sentences(id),
                region_code VARCHAR NOT NULL,
                translation_text TEXT NOT NULL,
                verified BOOLEAN DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (sentence_id, region_code)
            )
            """))
    # Create index on region_code for efficient queries
    session.execute(
        text(
            "CREATE INDEX ix_sentence_regional_variants_region_code ON sentence_regional_variants(region_code)"
        )
    )
    session.commit()
    print("Table 'sentence_regional_variants' created successfully")
    return True


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add regional variant tables")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
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

    # Create session
    session = create_database_session(args.db_path)

    try:
        # Create tables
        lemma_created = create_lemma_regional_variants_table(session, dry_run=args.dry_run)
        sentence_created = create_sentence_regional_variants_table(session, dry_run=args.dry_run)

        if args.dry_run:
            print("\n** DRY RUN - No changes were made **")
        else:
            tables_created = sum([lemma_created, sentence_created])
            print(f"\n** Migration complete - {tables_created} table(s) created **")

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
