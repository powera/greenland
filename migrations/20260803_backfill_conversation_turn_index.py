#!/usr/bin/env python3
"""
Migration: Backfill ``conversation_sentences.turn_index``.

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

Schema creation is handled by normal model initialization. This migration is
idempotent and backend-agnostic: it only fills rows whose turn index is NULL.

Usage:
    python migrations/20260803_backfill_conversation_turn_index.py
    python migrations/20260803_backfill_conversation_turn_index.py --postgres
    python migrations/20260803_backfill_conversation_turn_index.py --dry-run
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import text

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
        description="Backfill conversation_sentences.turn_index from position"
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

    backfill_turn_index(config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
