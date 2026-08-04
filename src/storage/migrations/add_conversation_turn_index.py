#!/usr/bin/env python3
"""
Migration: Add ``conversation_sentences.turn_index`` and backfill it.

A dialog turn used to be stored as one ``Sentence`` row even when the speaker
said several sentences, which broke the "one Sentence = one sentence" invariant
that translation, decomposition, audio alignment and ``minimum_level``-as-a-gate
all assume. Splitting turns into sentences means ``position`` can no longer
identify a turn, so a turn needs its own column: several rows share a
``turn_index`` when one turn ran to several sentences.

The column is nullable and deliberately *not* unique per conversation. The
alternative -- inferring turns by grouping consecutive same-speaker rows -- is
wrong, because a speaker can genuinely hold two consecutive turns (a pause, an
interruption that gets no reply), and grouping would silently merge them.

Backfill sets ``turn_index = position`` for every existing row. That is exact
rather than approximate: every row written before this migration *is* one whole
turn. Existing conversations are not split retroactively; they keep their
multi-sentence rows until regenerated.

This migration is idempotent and backend-agnostic: it creates whatever is
missing in the configured backend (SQLite locally, PostgreSQL in production)
and does nothing for parts that already exist.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_conversation_turn_index.py
    PYTHONPATH=src python src/storage/migrations/add_conversation_turn_index.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_conversation_turn_index.py --dry-run
"""

import argparse
import sys
from pathlib import Path

# Add src to path
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect, text

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import ConversationSentence


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=db_path,
    )


def add_turn_index_column(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Add the ``turn_index`` column to conversation_sentences if missing.

    Args:
        config: Storage configuration selecting the backend.
        dry_run: If True, report what would happen without altering the table.

    Returns:
        True if the column was added (or would be), False if it already existed
        or the table does not exist.
    """
    table_name = ConversationSentence.__tablename__
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            print(f"Table '{table_name}' does not exist; nothing to do.")
            return False

        columns = {col["name"] for col in inspector.get_columns(table_name)}
        if "turn_index" in columns:
            print(f"Column '{table_name}.turn_index' already exists; nothing to do.")
            return False

        if dry_run:
            print(f"Would add column '{table_name}.turn_index' (INTEGER, nullable) + index.")
            return True

        print(f"Adding column '{table_name}.turn_index'...")
        session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN turn_index INTEGER"))
        session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_turn_index "
                f"ON {table_name} (turn_index)"
            )
        )
        session.commit()
        print("Column added successfully.")
        return True
    finally:
        session.close()


def backfill_turn_index(config: DataSourceConfig, *, dry_run: bool = False) -> int:
    """Set ``turn_index = position`` for rows that do not have one yet.

    Exact for all pre-split data: one row was one turn. Rows written by the
    scene handler after the split already carry a turn_index and are left alone.

    Args:
        config: Storage configuration selecting the backend.
        dry_run: If True, report the row count without writing.

    Returns:
        Number of rows updated (or that would be).
    """
    table_name = ConversationSentence.__tablename__
    session = create_session(config)
    try:
        bind = session.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            print(f"Table '{table_name}' does not exist; nothing to backfill.")
            return 0
        columns = {col["name"] for col in inspector.get_columns(table_name)}
        if "turn_index" not in columns:
            print(f"Column '{table_name}.turn_index' does not exist yet; nothing to backfill.")
            return 0

        pending = session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE turn_index IS NULL")
        ).scalar()
        pending_count = int(pending or 0)
        if pending_count == 0:
            print("Every row already has a turn_index; nothing to backfill.")
            return 0

        if dry_run:
            print(f"Would set turn_index = position on {pending_count} row(s).")
            return pending_count

        print(f"Backfilling turn_index = position on {pending_count} row(s)...")
        session.execute(
            text(f"UPDATE {table_name} SET turn_index = position WHERE turn_index IS NULL")
        )
        session.commit()
        print("Backfill complete.")
        return pending_count
    finally:
        session.close()


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(
        description="Add conversation_sentences.turn_index and backfill it from position"
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

    add_turn_index_column(config, dry_run=args.dry_run)
    backfill_turn_index(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
