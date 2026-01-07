"""Common command-line argument patterns and utilities for agents.

This module provides reusable argument parser functions and utilities
to standardize command-line interfaces across all agents.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from constants import DEFAULT_MODEL


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add common arguments that nearly all agents use.

    Args:
        parser: The argument parser to add arguments to

    Returns:
        The same parser with common arguments added
    """
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to database file (default: inferred from environment)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        dest="yes",
        help="Skip confirmation prompts and proceed automatically",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing to database",
    )

    return parser


def add_llm_args(
    parser: argparse.ArgumentParser, default_model: str = DEFAULT_MODEL
) -> argparse.ArgumentParser:
    """Add LLM-related arguments.

    Args:
        parser: The argument parser to add arguments to
        default_model: Default model to use

    Returns:
        The same parser with LLM arguments added
    """
    parser.add_argument(
        "--model",
        type=str,
        default=default_model,
        help=f"LLM model to use (default: {default_model})",
    )

    parser.add_argument(
        "--throttle",
        type=float,
        default=1.0,
        help="Delay in seconds between LLM API calls (default: 1.0)",
    )

    parser.add_argument(
        "--barsukas-url",
        type=str,
        default=None,
        help="URL of BARSUKAS server to query for cached translations (e.g., http://server:5000)",
    )

    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Only use cached translations from --barsukas-url; fail if not in cache (requires --barsukas-url)",
    )

    return parser


def add_output_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add output-related arguments.

    Args:
        parser: The argument parser to add arguments to

    Returns:
        The same parser with output arguments added
    """
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for results/reports",
    )

    return parser


def add_processing_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add processing control arguments.

    Args:
        parser: The argument parser to add arguments to

    Returns:
        The same parser with processing arguments added
    """
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of items to process",
    )

    parser.add_argument(
        "--sample-rate",
        type=float,
        default=1.0,
        help="Fraction of items to process (0.0-1.0, default: 1.0)",
    )

    return parser


def add_guid_arg(
    parser: argparse.ArgumentParser, help_text: str = "Process only the item with this GUID"
) -> argparse.ArgumentParser:
    """Add --guid argument for processing a single item.

    Args:
        parser: The argument parser to add arguments to
        help_text: Custom help text for the GUID argument

    Returns:
        The same parser with GUID argument added
    """
    parser.add_argument(
        "--guid",
        type=str,
        default=None,
        help=help_text,
    )

    return parser


def add_backend_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add storage backend arguments.

    Args:
        parser: The argument parser to add arguments to

    Returns:
        The same parser with backend arguments added
    """
    parser.add_argument(
        "--backend",
        choices=["sqlite", "jsonl"],
        help="Storage backend type (default: sqlite, or use STORAGE_BACKEND env var)",
    )
    parser.add_argument(
        "--data-dir",
        help="Data directory for JSONL backend (e.g., data/release/lemmas). Only used with --backend jsonl",
    )

    return parser


def add_language_args(
    parser: argparse.ArgumentParser, multiple: bool = False
) -> argparse.ArgumentParser:
    """Add language-related arguments.

    Args:
        parser: The argument parser to add arguments to
        multiple: If True, allow multiple languages; if False, allow only one

    Returns:
        The same parser with language arguments added
    """
    if multiple:
        parser.add_argument(
            "--language",
            "--languages",
            type=str,
            nargs="+",
            dest="languages",
            help="Language code(s) to process (e.g., 'en', 'es', 'fr')",
        )
    else:
        parser.add_argument(
            "--language",
            type=str,
            default=None,
            help="Language code to process (e.g., 'en', 'es', 'fr')",
        )

    return parser


def validate_cache_args(args: Any) -> None:
    """Validate cache-related arguments.

    Args:
        args: Parsed arguments namespace

    Raises:
        SystemExit: If validation fails
    """
    if hasattr(args, "cache_only") and args.cache_only:
        if not hasattr(args, "barsukas_url") or not args.barsukas_url:
            print("Error: --cache-only requires --barsukas-url to be specified")
            sys.exit(1)


def confirm_operation(
    message: str,
    estimated_calls: Optional[int] = None,
    skip_confirmation: bool = False,
    dry_run: bool = False,
) -> bool:
    """Confirm an operation with the user.

    Args:
        message: Custom message to display (or None to use default)
        estimated_calls: Number of estimated LLM API calls (if applicable)
        skip_confirmation: If True, skip confirmation and return True
        dry_run: If True, this is a dry run (affects messaging)

    Returns:
        True if user confirms or confirmation is skipped, False otherwise
    """
    if skip_confirmation or dry_run:
        if dry_run:
            print("[DRY RUN MODE - No changes will be committed]\n")
        return True

    print()
    if estimated_calls is not None:
        print(f"This will make approximately {estimated_calls} LLM API calls.")
    if message:
        print(message)

    response = input("Do you want to proceed? [y/N]: ").strip().lower()
    if response not in ["y", "yes"]:
        print("Aborted.")
        return False

    print()
    return True


def count_items_for_confirmation(
    session_factory: Callable,
    query_builder: Callable,
    args: Any,
    multiplier: int = 1,
) -> int:
    """Count items that will be processed, for confirmation prompts.

    This is a helper to standardize the counting logic used before
    confirming LLM operations.

    Args:
        session_factory: Callable that returns a database session
        query_builder: Callable that takes a session and args and returns a query
        args: Namespace with --limit and --sample-rate options
        multiplier: Multiply the count by this (e.g., for multiple voices/languages)

    Returns:
        Estimated number of items/API calls
    """
    session = session_factory()
    try:
        query = query_builder(session, args)

        if hasattr(args, "limit") and args.limit:
            query = query.limit(args.limit)

        count = query.count()

        if hasattr(args, "sample_rate") and args.sample_rate < 1.0:
            count = int(count * args.sample_rate)

        return count * multiplier
    finally:
        session.close()


def get_standard_db_path(args_db_path: Optional[str] = None) -> str:
    """Get standardized database path with fallback logic.

    Args:
        args_db_path: Database path from command-line args (or None)

    Returns:
        Resolved database path
    """
    if args_db_path:
        return args_db_path

    # Try environment variable
    import os

    if "GREENLAND_DB" in os.environ:
        return os.environ["GREENLAND_DB"]

    # Default fallback
    return str(Path(__file__).parent.parent.parent / "data" / "greenland.db")


def get_data_source_config(args: Any, default_model: Optional[str] = None):
    """Create DataSourceConfig from parsed arguments.

    Args:
        args: Parsed arguments with backend, cache, and LLM-related attributes
        default_model: Default LLM model if not specified in args

    Returns:
        DataSourceConfig instance (always returns a valid config)
    """
    import constants
    from wordfreq.storage.backend.config import BackendType, DataSourceConfig

    # Determine backend type and paths
    backend_type = None
    sqlite_path = None
    jsonl_data_dir = None

    if hasattr(args, "backend") and args.backend:
        if args.backend == "sqlite":
            backend_type = BackendType.SQLITE
            sqlite_path = (
                args.db_path
                if hasattr(args, "db_path") and args.db_path
                else constants.WORDFREQ_DB_PATH
            )
        elif args.backend == "jsonl":
            if not hasattr(args, "data_dir") or not args.data_dir:
                print("Error: --data-dir is required when using --backend jsonl")
                sys.exit(1)
            backend_type = BackendType.JSONL
            jsonl_data_dir = args.data_dir
    elif hasattr(args, "db_path") and args.db_path:
        # Backward compatibility: db_path implies SQLite backend
        backend_type = BackendType.SQLITE
        sqlite_path = args.db_path

    # If no backend specified, use default SQLite backend
    if backend_type is None:
        backend_type = BackendType.SQLITE
        sqlite_path = constants.WORDFREQ_DB_PATH

    # Get cache configuration
    barsukas_url = args.barsukas_url if hasattr(args, "barsukas_url") else None
    cache_only = args.cache_only if hasattr(args, "cache_only") else False

    # Get LLM model (prefer args.model, fall back to default_model or DEFAULT_MODEL)
    model = (
        args.model if hasattr(args, "model") and args.model else (default_model or DEFAULT_MODEL)
    )

    # Get debug flag
    debug = args.debug if hasattr(args, "debug") else False

    return DataSourceConfig(
        backend_type=backend_type,
        sqlite_path=sqlite_path,
        jsonl_data_dir=jsonl_data_dir,
        barsukas_url=barsukas_url,
        cache_only=cache_only,
        model=model,
        debug=debug,
    )
