#!/usr/bin/python3

"""
Migration script to create sentence-related tables.

This script creates three new tables:
1. sentences - Stores sentence metadata (pattern, tense, difficulty level)
2. sentence_translations - Stores sentence text in multiple languages
3. sentence_words - Links sentences to the words/lemmas they use

The sentence tables enable tracking which vocabulary words are needed
to understand a sentence, allowing calculation of minimum difficulty level.
"""

import logging
from sqlalchemy import inspect

from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Base, Sentence, SentenceTranslation, SentenceWord

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def verify_tables_exist(session):
    """
    Verify that sentence tables exist in the database.

    Args:
        session: Database session

    Returns:
        dict: Status of each table (exists: bool)
    """
    engine = session.get_bind().engine
    inspector = inspect(engine)

    tables_to_check = {
        'sentences': Sentence,
        'sentence_translations': SentenceTranslation,
        'sentence_words': SentenceWord
    }

    status = {}
    for table_name, model_class in tables_to_check.items():
        exists = inspector.has_table(table_name)
        status[table_name] = exists

        if exists:
            columns = inspector.get_columns(table_name)
            logger.info(f"✓ Table '{table_name}' exists with {len(columns)} columns")
            for col in columns:
                logger.debug(f"  - {col['name']}: {col['type']}")
        else:
            logger.warning(f"✗ Table '{table_name}' does not exist")

    return status


def create_sentence_tables(session, force=False):
    """
    Create sentence-related tables if they don't exist.

    Args:
        session: Database session
        force: If True, drop and recreate tables (USE WITH CAUTION)

    Returns:
        dict: Status of table creation
    """
    engine = session.get_bind().engine

    if force:
        logger.warning("Force mode enabled - dropping existing tables!")
        # Only drop sentence-related tables, not all tables
        SentenceWord.__table__.drop(engine, checkfirst=True)
        SentenceTranslation.__table__.drop(engine, checkfirst=True)
        Sentence.__table__.drop(engine, checkfirst=True)

    logger.info("Creating sentence tables...")

    # Create all tables (will skip existing ones)
    Base.metadata.create_all(engine)

    # Verify creation
    status = verify_tables_exist(session)

    if all(status.values()):
        logger.info("✓ All sentence tables created successfully!")
    else:
        logger.error("✗ Some tables failed to create")
        for table_name, exists in status.items():
            if not exists:
                logger.error(f"  Missing: {table_name}")

    return status


def show_schema_info(session):
    """
    Display detailed schema information for sentence tables.

    Args:
        session: Database session
    """
    engine = session.get_bind().engine
    inspector = inspect(engine)

    tables = ['sentences', 'sentence_translations', 'sentence_words']

    for table_name in tables:
        if not inspector.has_table(table_name):
            logger.warning(f"\nTable '{table_name}' does not exist")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"Table: {table_name}")
        logger.info(f"{'='*60}")

        # Show columns
        columns = inspector.get_columns(table_name)
        logger.info("\nColumns:")
        for col in columns:
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            default = f", DEFAULT={col['default']}" if col['default'] else ""
            logger.info(f"  {col['name']:<25} {col['type']:<15} {nullable}{default}")

        # Show indexes
        indexes = inspector.get_indexes(table_name)
        if indexes:
            logger.info("\nIndexes:")
            for idx in indexes:
                unique = "UNIQUE " if idx['unique'] else ""
                logger.info(f"  {unique}{idx['name']}: {idx['column_names']}")

        # Show foreign keys
        foreign_keys = inspector.get_foreign_keys(table_name)
        if foreign_keys:
            logger.info("\nForeign Keys:")
            for fk in foreign_keys:
                logger.info(f"  {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")

        # Show unique constraints
        unique_constraints = inspector.get_unique_constraints(table_name)
        if unique_constraints:
            logger.info("\nUnique Constraints:")
            for uc in unique_constraints:
                logger.info(f"  {uc['name']}: {uc['column_names']}")


def main():
    """Main entry point for migration script."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Create sentence tables in the database'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify tables exist without creating them'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Drop and recreate tables (WARNING: destroys data!)'
    )
    parser.add_argument(
        '--schema',
        action='store_true',
        help='Show detailed schema information'
    )

    args = parser.parse_args()

    session = create_database_session()

    try:
        if args.verify:
            logger.info("Verifying sentence tables...")
            status = verify_tables_exist(session)
            if all(status.values()):
                logger.info("\n✓ All sentence tables exist")
                if args.schema:
                    show_schema_info(session)
                return 0
            else:
                logger.error("\n✗ Some tables are missing")
                return 1
        else:
            status = create_sentence_tables(session, force=args.force)
            if args.schema:
                show_schema_info(session)
            return 0 if all(status.values()) else 1

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1
    finally:
        session.close()


if __name__ == '__main__':
    exit(main())
