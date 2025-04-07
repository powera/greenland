#!/usr/bin/python3

"""Migration script to transition from old database schema to new schema."""

import logging
import sys
import time
from typing import Dict, Any

import constants
from wordfreq import linguistic_db
from wordfreq.connection_pool import get_session, close_thread_sessions

# Import SQLAlchemy's inspect functionality
from sqlalchemy import inspect

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backup_database(db_path: str) -> str:
    """
    Create a backup of the database before migration.
    
    Args:
        db_path: Path to the database file
        
    Returns:
        Path to the backup file
    """
    import shutil
    import datetime
    
    # Create timestamp for backup file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    # Copy the database file
    shutil.copy2(db_path, backup_path)
    
    logger.info(f"Created database backup at {backup_path}")
    return backup_path

def check_database_structure(session) -> Dict[str, Any]:
    """
    Check if the database has old schema, new schema, or both.
    
    Args:
        session: Database session
        
    Returns:
        Dictionary with database structure information
    """
    # Get the inspector properly using SQLAlchemy's inspect function
    inspector = inspect(session.bind)
    table_names = inspector.get_table_names()
    
    has_old_schema = 'parts_of_speech' in table_names and 'lemmas' in table_names
    has_new_schema = 'definitions' in table_names and 'examples' in table_names
    
    return {
        "has_old_schema": has_old_schema,
        "has_new_schema": has_new_schema,
        "all_tables": table_names
    }

def run_migration(db_path: str, create_backup: bool = True, verbose: bool = False) -> Dict[str, Any]:
    """
    Run migration from old schema to new schema.
    
    Args:
        db_path: Path to the database file
        create_backup: Whether to create a backup before migration
        verbose: Whether to print detailed progress
        
    Returns:
        Dictionary with migration statistics
    """
    # Create backup if requested
    if create_backup:
        backup_path = backup_database(db_path)
        logger.info(f"Backup created at {backup_path}")
    
    # Create session
    session = get_session(db_path, echo=verbose)
    
    # Check database structure
    db_structure = check_database_structure(session)
    logger.info(f"Database structure: {db_structure}")
    
    if not db_structure["has_old_schema"]:
        return {"error": "Old schema tables not found"}
    
    # Ensure new schema tables exist
    linguistic_db.ensure_tables_exist(session)
    
    # Run migration
    logger.info("Starting migration...")
    start_time = time.time()
    stats = linguistic_db.migrate_from_old_schema(session)
    end_time = time.time()
    
    # Log results
    if "error" in stats:
        logger.error(f"Migration failed: {stats['error']}")
    else:
        logger.info("Migration completed successfully:")
        logger.info(f"  Words processed: {stats['words_processed']}")
        logger.info(f"  Definitions created: {stats['definitions_created']}")
        logger.info(f"  Words with POS but no lemma: {stats['words_with_pos_but_no_lemma']}")
        logger.info(f"  Words with lemma but no POS: {stats['words_with_lemma_but_no_pos']}")
        logger.info(f"Time taken: {end_time - start_time:.2f} seconds")
        
        # Add time information to stats
        stats["time_seconds"] = end_time - start_time
    
    # Close session
    session.close()
    close_thread_sessions()
    
    return stats

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate from old database schema to new schema")
    parser.add_argument("--db", default=constants.WORDFREQ_DB_PATH, help="Database file path")
    parser.add_argument("--no-backup", action="store_true", help="Skip database backup")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--check-only", action="store_true", help="Only check database structure without migrating")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Set up database session
    session = get_session(args.db, echo=args.verbose)
    
    if args.check_only:
        # Just check structure and exit
        db_structure = check_database_structure(session)
        print("Database structure:")
        print(f"  Has old schema (parts_of_speech, lemmas): {db_structure['has_old_schema']}")
        print(f"  Has new schema (definitions, examples): {db_structure['has_new_schema']}")
        print(f"  All tables: {', '.join(db_structure['all_tables'])}")
        session.close()
        return
    
    # Run migration
    try:
        print(f"Starting migration of database: {args.db}")
        print(f"Creating backup: {'No' if args.no_backup else 'Yes'}")
        
        # Confirm before proceeding
        confirm = input("Continue with migration? (y/n): ").strip().lower()
        if confirm != 'y' and confirm != 'yes':
            print("Migration cancelled.")
            return
        
        stats = run_migration(args.db, create_backup=not args.no_backup, verbose=args.verbose)
        
        if "error" in stats:
            print(f"Migration failed: {stats['error']}")
        else:
            print("Migration completed successfully:")
            print(f"  Words processed: {stats['words_processed']}")
            print(f"  Definitions created: {stats['definitions_created']}")
            print(f"  Words with POS but no lemma: {stats['words_with_pos_but_no_lemma']}")
            print(f"  Words with lemma but no POS: {stats['words_with_lemma_but_no_pos']}")
            print(f"  Time taken: {stats['time_seconds']:.2f} seconds")
    
    except KeyboardInterrupt:
        print("\nMigration cancelled by user.")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        session.close()
        close_thread_sessions()

if __name__ == "__main__":
    main()