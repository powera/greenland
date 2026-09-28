#!/usr/bin/env python3
"""
Migration: Create the ``curriculum_levels`` table, optionally loading it from
``data/release/levels``.

The table holds display and sequencing metadata for level numbers -- a name
per UI language, a CEFR estimate, prerequisites -- which the wireword manifest
ships as ``config.levels``. See ``storage.models.curriculum_level``.

``create_session`` already runs ``create_all`` and makes the table on its own;
this migration exists so the change is explicit and so a fresh table can be
populated from the release file in the same step. Both steps are
idempotent: an existing table is left alone, and the release import upserts on
the level number.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python migrations/20260928_create_curriculum_levels_table.py --dry-run
    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20260928_create_curriculum_levels_table.py --import-release
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import inspect

from constants import RELEASE_DIR, WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.curriculum_level import CurriculumLevel
from storage.release import curriculum_level as level_release

_TABLE_NAME = CurriculumLevel.__tablename__


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Create the curriculum_levels table")
    parser.add_argument("--dry-run", action="store_true", help="Report without changing anything")
    parser.add_argument(
        "--import-release",
        action="store_true",
        help="Also load data/release/levels into the table",
    )
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH, help="Path to SQLite database")
    parser.add_argument("--postgres", action="store_true", help="Use PostgreSQL instead of SQLite")
    args = parser.parse_args()

    config = build_data_source_config(args.db_path, args.postgres)
    release_dir = Path(RELEASE_DIR) / level_release.RELEASE_DIRNAME
    print(f"Database: {config.postgres_url if args.postgres else config.sqlite_path}")

    if args.dry_run:
        count = len(level_release.read_release_records(release_dir))
        print(f"Would ensure table {_TABLE_NAME} exists.")
        if args.import_release:
            print(f"Would import {count} level record(s) from {release_dir}.")
        print("\n** DRY RUN - No changes were made **")
        return 0

    # create_session runs create_all, which makes the table when it is absent
    # and leaves an existing one alone; the explicit create below only matters
    # for a backend that skips that step.
    session = create_session(config)
    try:
        bind = session.get_bind()
        if _TABLE_NAME in inspect(bind).get_table_names():
            print(f"Table {_TABLE_NAME} is present.")
        else:
            CurriculumLevel.metadata.tables[_TABLE_NAME].create(bind)
            print(f"Created table {_TABLE_NAME}.")

        if args.import_release:
            count = level_release.import_from_release(session, release_dir)
            print(f"Imported {count} level record(s) from {release_dir}.")
    finally:
        session.close()

    print("\n** Migration complete **")
    return 0


if __name__ == "__main__":
    sys.exit(main())
