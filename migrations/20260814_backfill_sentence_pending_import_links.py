#!/usr/bin/env python3
"""
Migration: Backfill sentence_pending_imports from legacy word hints.

A sentence that stages a word it could not link needs a back-link to the staged
term, or nothing can re-link the sentence once the term is approved. That link
used to live in ``sentence_word_hints.pending_import_id``, which collided with
the hint table's ``(sentence_id, position)`` uniqueness and had to be released
by hand from every path that deleted a pending import.

Normal model initialization creates the dedicated link table. This migration
copies every live hint reference into it. The hint column is deliberately left alone: nothing writes it any more, and
``words.pending_imports.sentence_links.release_legacy_hints`` still cleans up
whatever is left when the pending row it points at is deleted.

Usage:
    python migrations/20260814_backfill_sentence_pending_import_links.py
    python migrations/20260814_backfill_sentence_pending_import_links.py --postgres
    python migrations/20260814_backfill_sentence_pending_import_links.py --dry-run
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.models.schema import SentenceWordHint
from words.pending_imports.sentence_links import backfill_links_from_hints


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)


def count_legacy_hints(session: Session) -> int:
    """How many hint rows still carry a pending import reference."""
    return int(
        session.query(SentenceWordHint)
        .filter(SentenceWordHint.pending_import_id.isnot(None))
        .count()
    )


def migrate(config: DataSourceConfig, *, dry_run: bool = False) -> int:
    """Create links for legacy hints and return the number created or pending."""
    session = create_session(config)
    try:
        if dry_run:
            pending_count = count_legacy_hints(session)
            print(f"Would backfill from {pending_count} hint row(s).")
            return pending_count

        created_count = int(backfill_links_from_hints(session))
        session.commit()
        print(f"Backfilled {created_count} sentence link(s) from word hints.")
        return created_count
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(
        description="Backfill sentence_pending_imports from legacy word hints"
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
    parser.add_argument(
        "--postgres",
        action="store_true",
        help="Use PostgreSQL instead of SQLite",
    )

    args = parser.parse_args()
    config = build_data_source_config(args.db_path, args.postgres)
    database_label = config.postgres_url if args.postgres else config.sqlite_path

    print(f"Database: {database_label}")
    print(f"Backend: {config.backend_type.value}")
    print(f"Dry run: {args.dry_run}")
    print()

    migrate(config, dry_run=args.dry_run)
    if args.dry_run:
        print("\n** DRY RUN - No changes were made **")
    else:
        print("\n** Migration complete **")
    return 0


if __name__ == "__main__":
    sys.exit(main())
