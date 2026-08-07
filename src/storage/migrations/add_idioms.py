#!/usr/bin/env python3
"""Create the idioms and idiom_equivalents tables.

Usage:
    PYTHONPATH=src python src/storage/migrations/add_idioms.py
    PYTHONPATH=src python src/storage/migrations/add_idioms.py --postgres
    PYTHONPATH=src python src/storage/migrations/add_idioms.py --dry-run
"""

import argparse
import sys
from pathlib import Path
from typing import cast

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Engine, Table, create_engine, inspect

from constants import WORDFREQ_DB_PATH
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.idiom import Idiom, IdiomEquivalent


def _create_migration_engine(config: DataSourceConfig) -> Engine:
    """Create an engine without the application factory's automatic create_all."""
    if config.backend_type == BackendType.POSTGRES:
        if config.postgres_url is None:
            raise ValueError("postgres_url is required for PostgreSQL")
        return create_engine(config.postgres_url)
    if config.sqlite_path is None:
        raise ValueError("sqlite_path is required for SQLite")
    return create_engine(f"sqlite:///{config.sqlite_path}")


def create_idiom_tables(config: DataSourceConfig, *, dry_run: bool = False) -> bool:
    """Create missing idiom tables selected by ``config`` idempotently."""
    engine = _create_migration_engine(config)
    created_any = False
    try:
        inspector = inspect(engine)
        for model in (Idiom, IdiomEquivalent):
            table_name = model.__tablename__
            if inspector.has_table(table_name):
                continue
            if not dry_run:
                cast(Table, model.__table__).create(engine, checkfirst=True)
            created_any = True
        return created_any
    finally:
        engine.dispose()


def _parse_config(use_postgres: bool) -> DataSourceConfig:
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=WORDFREQ_DB_PATH,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    create_idiom_tables(_parse_config(args.postgres), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
