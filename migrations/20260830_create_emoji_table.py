#!/usr/bin/env python3
"""
Migration: Create the ``emoji`` table and seed it from the emoji catalog.

Emoji assignment used to live only as a JSON list on ``Lemma.emoji``. That
column stays -- it is what the release round trip serializes into
``data/release`` -- but it cannot hold the two review outcomes that are not an
assignment ("nothing depicts this glyph", "this glyph names a word we do not
have yet"), and it cannot enforce that a glyph belongs to at most one lemma.

The ``emoji`` table carries both. Seeding it with the pictographic Unicode
blocks turns populating emoji into a finite walk: every glyph starts
``undecided`` and each review moves it to a terminal state.

Seed rows come from ``src/words/data/emoji_catalog.json`` rather than the
running Python's Unicode tables, so the row set does not shift under a Python
upgrade. Both creating the table and seeding it are idempotent: an existing
table is left alone, and a glyph that already has a row is never re-inserted,
so a re-run cannot clobber a decision that has been made.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from typing import List

from sqlalchemy import Connection, Engine, inspect
from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.emoji import EMOJI_STATUS_UNDECIDED, Emoji
from words.emoji_catalog import CatalogEntry, load_catalog

_TABLE_NAME = "emoji"


def _bind(session: Session) -> Connection | Engine:
    """The session's bind, which every caller here needs for DDL."""
    bind = session.get_bind()
    if bind is None:  # pragma: no cover - a sessionmaker always binds
        raise RuntimeError("Session has no bind; cannot run DDL.")
    return bind


def table_exists(session: Session, table_name: str) -> bool:
    """Whether a table is already present in the database."""
    return table_name in inspect(_bind(session)).get_table_names()


def create_emoji_table(session: Session) -> bool:
    """Create the emoji table if absent. Returns True if it was created."""
    if table_exists(session, _TABLE_NAME):
        print(f"Table {_TABLE_NAME} already exists; leaving it alone.")
        return False
    Emoji.metadata.tables[_TABLE_NAME].create(_bind(session))
    session.commit()
    print(f"Created table {_TABLE_NAME}.")
    return True


def unseeded_entries(session: Session) -> List[CatalogEntry]:
    """Catalog entries that have no row yet."""
    known = {value for (value,) in session.query(Emoji.value)}
    return [entry for entry in load_catalog() if entry.value not in known]


def seed_catalog(session: Session) -> int:
    """Insert an undecided row for every catalog glyph not already present.

    Returns the number inserted. Existing rows are never touched, so this is
    safe to re-run after the catalog is regenerated with new glyphs.
    """
    pending = unseeded_entries(session)
    for entry in pending:
        session.add(
            Emoji(
                value=entry.value,
                unicode_name=entry.name,
                codepoint=entry.codepoint,
                block=entry.block,
                status=EMOJI_STATUS_UNDECIDED,
            )
        )
    if pending:
        session.commit()
    return len(pending)


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


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Create and seed the emoji table")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Create the table but do not insert catalog rows",
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

    session = create_session(config)
    try:
        if args.dry_run:
            if table_exists(session, _TABLE_NAME):
                print(f"Table {_TABLE_NAME} exists.")
                missing = len(unseeded_entries(session))
                print(f"Would seed {missing} catalog glyph(s).")
            else:
                print(f"Would create table {_TABLE_NAME}.")
                print(f"Would seed {len(load_catalog())} catalog glyph(s).")
            print("\n** DRY RUN - No changes were made **")
        else:
            create_emoji_table(session)
            if args.no_seed:
                print("Skipping seed (--no-seed).")
            else:
                seeded = seed_catalog(session)
                print(f"Seeded {seeded} catalog glyph(s).")
            print("\n** Migration complete **")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
