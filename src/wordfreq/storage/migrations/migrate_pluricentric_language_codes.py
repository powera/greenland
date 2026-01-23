#!/usr/bin/env python3
"""
Migration script to rename base language codes to explicit regional codes.

This migration updates language codes for pluricentric languages:
- zh → zh-CN (Simplified Chinese, Mainland Mandarin)
- es → es-ES (Castilian Spanish, Spain)
- pt → pt-BR (Brazilian Portuguese)

Affected tables:
- lemma_translations
- sentence_translations

Usage:
    # Dry run (no changes made)
    PYTHONPATH=src python src/wordfreq/storage/migrations/migrate_pluricentric_language_codes.py --dry-run

    # Apply migration
    PYTHONPATH=src python src/wordfreq/storage/migrations/migrate_pluricentric_language_codes.py --apply

    # With custom SQLite path
    PYTHONPATH=src python src/wordfreq/storage/migrations/migrate_pluricentric_language_codes.py --apply --sqlite-path /path/to/db.sqlite

    # With remote PostgreSQL (uses key file for password)
    PYTHONPATH=src python src/wordfreq/storage/migrations/migrate_pluricentric_language_codes.py --apply --backend postgres

    # With explicit PostgreSQL URL
    PYTHONPATH=src python src/wordfreq/storage/migrations/migrate_pluricentric_language_codes.py --apply --backend postgres --postgres-url postgresql://user:pass@host:5432/db
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from sqlalchemy import text
from sqlalchemy.orm import Session

from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.backend.factory import create_session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Language code mappings: old_code → new_code
LANGUAGE_CODE_MIGRATIONS = {
    "zh": "zh-CN",  # Chinese → Simplified Chinese (Mainland)
    "es": "es-ES",  # Spanish → Castilian Spanish (Spain)
    "pt": "pt-BR",  # Portuguese → Brazilian Portuguese
}


def count_affected_rows(session: Session, table_name: str, old_code: str) -> int:
    """Count rows that will be affected by the migration."""
    result = session.execute(
        text(f"SELECT COUNT(*) FROM {table_name} WHERE language_code = :code"),
        {"code": old_code},
    )
    return result.scalar() or 0


def migrate_table(
    session: Session, table_name: str, old_code: str, new_code: str, dry_run: bool
) -> int:
    """Migrate language codes in a single table."""
    count = count_affected_rows(session, table_name, old_code)

    if count == 0:
        logger.info(f"  {table_name}: No rows with code '{old_code}' found")
        return 0

    if dry_run:
        logger.info(f"  {table_name}: Would update {count} rows from '{old_code}' to '{new_code}'")
    else:
        result = session.execute(
            text(
                f"UPDATE {table_name} SET language_code = :new_code WHERE language_code = :old_code"
            ),
            {"old_code": old_code, "new_code": new_code},
        )
        logger.info(
            f"  {table_name}: Updated {result.rowcount} rows from '{old_code}' to '{new_code}'"
        )

    return count


def run_migration(config: DataSourceConfig, dry_run: bool = True) -> Dict[str, Any]:
    """
    Run the migration to rename language codes.

    Args:
        config: Database configuration
        dry_run: If True, only report what would be changed

    Returns:
        Dictionary with migration statistics
    """
    session = create_session(config)
    stats: Dict[str, Any] = {
        "tables_affected": 0,
        "rows_affected": 0,
        "migrations": {},
    }

    try:
        logger.info("=" * 60)
        logger.info("Pluricentric Language Code Migration")
        logger.info("=" * 60)
        logger.info(f"Mode: {'DRY RUN (no changes)' if dry_run else 'APPLY CHANGES'}")
        logger.info("")

        for old_code, new_code in LANGUAGE_CODE_MIGRATIONS.items():
            logger.info(f"Migrating '{old_code}' → '{new_code}':")
            migration_stats = {"lemma_translations": 0, "sentence_translations": 0}

            # Migrate lemma_translations
            count = migrate_table(session, "lemma_translations", old_code, new_code, dry_run)
            migration_stats["lemma_translations"] = count
            stats["rows_affected"] += count

            # Migrate sentence_translations
            count = migrate_table(session, "sentence_translations", old_code, new_code, dry_run)
            migration_stats["sentence_translations"] = count
            stats["rows_affected"] += count

            stats["migrations"][f"{old_code}→{new_code}"] = migration_stats
            logger.info("")

        if not dry_run:
            session.commit()
            logger.info("Migration committed successfully!")
        else:
            logger.info("Dry run complete. No changes were made.")
            logger.info("Run with --apply to apply changes.")

        logger.info("")
        logger.info("=" * 60)
        logger.info("Summary")
        logger.info("=" * 60)
        logger.info(f"Total rows affected: {stats['rows_affected']}")
        for migration_key, migration_counts in stats["migrations"].items():
            logger.info(f"  {migration_key}:")
            for table, count in migration_counts.items():
                logger.info(f"    {table}: {count}")

        return stats

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    """CLI entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate pluricentric language codes (zh→zh-CN, es→es-ES, pt→pt-BR)"
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration (make changes to the database)",
    )

    # Backend options
    parser.add_argument(
        "--backend",
        choices=["sqlite", "postgres"],
        default="sqlite",
        help="Database backend type (default: sqlite)",
    )
    parser.add_argument(
        "--sqlite-path",
        help="Path to SQLite database (for sqlite backend, uses default if not specified)",
    )
    parser.add_argument(
        "--postgres-url",
        help="PostgreSQL connection URL (e.g., postgresql://user:pass@host:5432/db)",
    )

    args = parser.parse_args()

    # Build config
    if args.backend == "sqlite":
        config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=args.sqlite_path,
        )
    else:
        if not args.postgres_url:
            # Try to build URL from key file and template
            config = DataSourceConfig(
                backend_type=BackendType.POSTGRES,
                postgres_url=DataSourceConfig.build_postgres_url(),
            )
        else:
            config = DataSourceConfig(
                backend_type=BackendType.POSTGRES,
                postgres_url=args.postgres_url,
            )

    # Run migration
    dry_run = args.dry_run
    run_migration(config, dry_run=dry_run)


if __name__ == "__main__":
    main()
