#!/usr/bin/env python3
"""
Migration: Create sentence_pending_imports and backfill it from word hints.

A sentence that stages a word it could not link needs a back-link to the staged
term, or nothing can re-link the sentence once the term is approved. That link
used to live in ``sentence_word_hints.pending_import_id``, which collided with
the hint table's ``(sentence_id, position)`` uniqueness and had to be released
by hand from every path that deleted a pending import.

This creates the dedicated link table and copies every live hint reference into
it. The hint column is deliberately left alone: nothing writes it any more, and
``words.pending_imports.sentence_links.release_legacy_hints`` still cleans up
whatever is left when the pending row it points at is deleted.
"""

import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.database import create_database_session
from storage.models.imports import SentencePendingImport
from storage.models.schema import SentenceWordHint
from words.pending_imports.sentence_links import backfill_links_from_hints

_TABLE_NAME = "sentence_pending_imports"


def check_table_exists(session: Session, table_name: str) -> bool:
    """Check whether a table exists."""
    inspector = inspect(session.bind)
    return table_name in inspector.get_table_names()  # type: ignore[union-attr]


def create_link_table(session: Session) -> bool:
    """Create the link table if it does not exist. Returns True when created."""
    if check_table_exists(session, _TABLE_NAME):
        print(f"Table {_TABLE_NAME} already exists; nothing to create.")
        return False
    SentencePendingImport.__table__.create(session.bind)
    print(f"Created table {_TABLE_NAME}.")
    return True


def count_legacy_hints(session: Session) -> int:
    """How many hint rows still carry a pending import reference."""
    return int(
        session.query(SentenceWordHint)
        .filter(SentenceWordHint.pending_import_id.isnot(None))
        .count()
    )


def main() -> int:
    """Run the migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create sentence_pending_imports and backfill it from word hints"
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

    args = parser.parse_args()

    print(f"Database: {args.db_path}")
    print(f"Dry run: {args.dry_run}")
    print()

    session = create_database_session(args.db_path)
    try:
        if args.dry_run:
            if check_table_exists(session, _TABLE_NAME):
                print(f"Table {_TABLE_NAME} already exists")
            else:
                print(f"Would create table {_TABLE_NAME}")
            print(f"Would backfill from {count_legacy_hints(session)} hint row(s)")
            print("\n** DRY RUN - No changes were made **")
        else:
            create_link_table(session)
            created = backfill_links_from_hints(session)
            session.commit()
            print(f"Backfilled {created} sentence link(s) from word hints.")
            print("\n** Migration complete **")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
