"""Database maintenance CLI for an existing configured backend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_output_args,
    get_data_source_config,
)
from storage.admin.service import DatabaseAdminService


def get_argument_parser() -> argparse.ArgumentParser:
    """Build the database-administration argument parser."""
    parser = argparse.ArgumentParser(description="Database initialization and maintenance")
    add_common_args(parser)
    add_backend_args(parser)
    add_output_args(parser)

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check", action="store_true", help="Check configuration and database state"
    )
    mode_group.add_argument("--sync-config", action="store_true", help="Sync corpus configurations")
    mode_group.add_argument(
        "--load",
        nargs="*",
        metavar="CORPUS",
        help="Load specified corpora, or all enabled corpora when no names are given",
    )
    mode_group.add_argument("--import-tiers", action="store_true")
    mode_group.add_argument(
        "--link-forms",
        action="store_true",
        help="Link derivative/variant forms to their word tokens. Runs inside "
        "--repopulate; needed on its own only between a bare --load and --calc-ranks, "
        "since the rank rollup skips any form with no word_token_id",
    )
    mode_group.add_argument("--calc-ranks", action="store_true")
    mode_group.add_argument(
        "--clear-wordfreq",
        action="store_true",
        help="Delete every corpus-derived row (word tokens, wordfreq annotations, "
        "form links). Lemmas, forms and tier data are kept",
    )
    mode_group.add_argument(
        "--repopulate",
        action="store_true",
        help="Clear all wordfreq data and rebuild it end to end: sync config, load "
        "corpora, link forms, import tiers, calculate ranks. The single entry point "
        "for a full refresh from the corpus files",
    )
    return parser


def _write_result(output_path: Optional[str], result: dict[str, Any]) -> None:
    if output_path is None:
        return
    Path(output_path).write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Run one administrative operation."""
    parser = get_argument_parser()
    args = parser.parse_args()
    config = get_data_source_config(args)
    service = DatabaseAdminService(config)

    if args.check:
        service.run_check(output_file=args.output)
        return
    if args.sync_config:
        result = service.sync_configurations(dry_run=args.dry_run)
    elif args.load is not None:
        corpus_names = args.load if args.load else None
        result = service.load_corpora(corpus_names=corpus_names, dry_run=args.dry_run)
    elif args.import_tiers:
        result = service.import_tiers(dry_run=args.dry_run)
    elif args.link_forms:
        result = service.link_forms_to_word_tokens(dry_run=args.dry_run)
    elif args.calc_ranks:
        result = service.calculate_ranks(dry_run=args.dry_run)
    elif args.clear_wordfreq:
        result = service.clear_wordfreq_data(dry_run=args.dry_run)
    elif args.repopulate:
        result = service.initialize_database(dry_run=args.dry_run, clear=True)
    else:
        service.run_check(output_file=args.output)
        return

    _write_result(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
