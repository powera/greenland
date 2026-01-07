#!/usr/bin/env python3
"""
Migration: Add definition_text to LemmaTranslation and migrate English data.

This migration:
1. Adds definition_text column to lemma_translations table
2. Creates English translation rows for all lemmas using existing lemma_text/definition_text
3. Preserves existing translation rows
"""

import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sqlalchemy import inspect, text

from constants import WORDFREQ_DB_PATH
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, LemmaTranslation


def check_column_exists(session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table.

    Args:
        session: Database session
        table_name: Name of the table
        column_name: Name of the column

    Returns:
        True if column exists, False otherwise
    """
    inspector = inspect(session.bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_definition_column(session):
    """Add definition_text column to lemma_translations table if it doesn't exist.

    Args:
        session: Database session
    """
    if check_column_exists(session, "lemma_translations", "definition_text"):
        print("Column 'definition_text' already exists in lemma_translations table")
        return False

    print("Adding 'definition_text' column to lemma_translations table...")
    session.execute(text("ALTER TABLE lemma_translations ADD COLUMN definition_text TEXT"))
    session.commit()
    print("Column added successfully")
    return True


def migrate_english_translations(session, dry_run: bool = False):
    """Create English translation rows for all lemmas.

    Args:
        session: Database session
        dry_run: If True, don't commit changes
    """
    print("\nMigrating English translations...")

    # Get all lemmas
    lemmas = session.query(Lemma).all()
    print(f"Found {len(lemmas)} lemmas")

    created = 0
    updated = 0
    skipped = 0

    for lemma in lemmas:
        # Check if English translation already exists
        existing_en = (
            session.query(LemmaTranslation)
            .filter(LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == "en")
            .first()
        )

        if existing_en:
            # Update existing translation with definition if not set
            if not existing_en.definition_text and lemma.definition_text:
                existing_en.definition_text = lemma.definition_text
                updated += 1
                if dry_run:
                    print(f"  Would update EN definition for lemma {lemma.id}: {lemma.lemma_text}")
            else:
                skipped += 1
        else:
            # Create new English translation row
            en_translation = LemmaTranslation(
                lemma_id=lemma.id,
                language_code="en",
                translation=lemma.lemma_text,
                definition_text=lemma.definition_text,
                verified=lemma.verified,
            )
            session.add(en_translation)
            created += 1

            if dry_run:
                print(f"  Would create EN translation for lemma {lemma.id}: {lemma.lemma_text}")

        # Commit in batches
        if (created + updated) % 100 == 0 and not dry_run:
            session.commit()

    if not dry_run:
        session.commit()

    print(f"\nMigration summary:")
    print(f"  Created: {created} new English translations")
    print(f"  Updated: {updated} existing English translations")
    print(f"  Skipped: {skipped} (already had English translation with definition)")

    return created, updated, skipped


def main():
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add definition_text to LemmaTranslation")
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
        # Step 1: Add column
        if not args.dry_run:
            column_added = add_definition_column(session)
        else:
            if check_column_exists(session, "lemma_translations", "definition_text"):
                print("Column 'definition_text' already exists")
                column_added = False
            else:
                print("Would add 'definition_text' column to lemma_translations table")
                column_added = True

        # Step 2: Migrate English data
        created, updated, skipped = migrate_english_translations(session, dry_run=args.dry_run)

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
