#!/usr/bin/env python3
"""Build the Greenland SQLite database from release data or from an empty schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import constants
from storage.admin.bootstrap import bootstrap_empty_database, bootstrap_from_release
from storage.backend.config import DataSourceConfig


def get_argument_parser() -> argparse.ArgumentParser:
    """Build the repository bootstrap argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=constants.WORDFREQ_DB_PATH,
        help=f"Destination SQLite database (default: {constants.WORDFREQ_DB_PATH})",
    )
    parser.add_argument(
        "--release-path",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "release",
        help="JSONL release root (default: data/release)",
    )
    parser.add_argument(
        "--empty",
        action="store_true",
        help="Skip data/release and initialize only schema, corpus, tier, and rank data",
    )
    parser.add_argument(
        "--release-only",
        action="store_true",
        help="Import data/release without local corpus, tier, and rank enrichment",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace a populated target when bootstrapping from release",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the empty-database workflow; not supported for release import",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the selected bootstrap workflow."""
    parser = get_argument_parser()
    args = parser.parse_args(argv)
    if args.empty and args.release_only:
        parser.error("--release-only cannot be combined with --empty")
    if args.empty and args.force:
        parser.error("--force applies only to release bootstrap")
    if not args.empty and args.dry_run:
        parser.error("--dry-run is supported only with --empty")

    config = DataSourceConfig(sqlite_path=args.db_path)
    if args.empty:
        result = bootstrap_empty_database(config, dry_run=args.dry_run)
    else:
        result = bootstrap_from_release(
            config,
            args.release_path,
            force=args.force,
            include_frequency_data=not args.release_only,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
