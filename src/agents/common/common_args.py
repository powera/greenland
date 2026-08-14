"""Common command-line argument patterns and utilities for agents.

This module provides reusable argument parser functions and utilities
to standardize command-line interfaces across all agents.
"""

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import constants
from barsukas.personas import PersonaName
from constants import DEFAULT_MODEL

if TYPE_CHECKING:
    from storage.backend.config import DataSourceConfig


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
    parser.add_argument(
        "--use-word2vec",
        "--use_word2vec",
        dest="use_word2vec",
        action="store_true",
        help="Enable pgvector embedding read/write operations (opt-in)",
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


# --persona value that unlocks the manual backend flags below. Not a real
# Barsukas persona: it means "the command line spells out the backend itself".
CUSTOM_PERSONA = "custom"

# Help-text marker for the manual backend flags. The Barsukas agents launcher
# hides any argument whose help starts with this; the launcher always passes
# a real persona instead.
ADVANCED_ARG_MARKER = "[ADVANCED]"


def add_backend_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add storage backend arguments.

    --persona is the way to select the main database. The manual flags
    (--backend/--data-dir/--postgres) are only honored together with
    --persona custom; get_data_source_config() rejects them otherwise.

    Args:
        parser: The argument parser to add arguments to

    Returns:
        The same parser with backend arguments added
    """
    parser.add_argument(
        "--persona",
        choices=[p.value for p in PersonaName] + [CUSTOM_PERSONA],
        help=(
            "Use the main database of this Barsukas persona (e.g. local, prod). "
            "Agents only use the persona's main database; its concepts and UI "
            "settings do not apply. 'custom' selects the backend from the manual "
            "--backend/--data-dir/--postgres flags instead."
        ),
    )
    parser.add_argument(
        "--backend",
        choices=["sqlite", "jsonl", "postgres"],
        help=f"{ADVANCED_ARG_MARKER} Requires --persona custom. Storage backend type (default: sqlite)",
    )
    parser.add_argument(
        "--data-dir",
        help=(
            f"{ADVANCED_ARG_MARKER} Requires --persona custom. Data directory for "
            "JSONL backend (e.g., data/release). Only used with --backend jsonl"
        ),
    )
    parser.add_argument(
        "--postgres",
        action="store_true",
        help=f"{ADVANCED_ARG_MARKER} Requires --persona custom. Use PostgreSQL backend instead of SQLite",
    )

    return parser


def add_language_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the standard multi-language CLI argument.

    Args:
        parser: The argument parser to add arguments to
    Returns:
        The same parser with language arguments added
    """
    # ``argparse`` accepts unique long-option prefixes by default, which would
    # otherwise make the removed ``--language`` spelling continue to work as an
    # abbreviation for ``--languages``.
    parser.allow_abbrev = False
    parser.add_argument(
        "--languages",
        type=str,
        nargs="+",
        dest="languages",
        help="Language code(s) to process (e.g., 'en', 'es', 'fr')",
    )

    return parser


def add_level_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add difficulty level filtering arguments.

    Supports both single levels (--level 5) and ranges (--level 1-9).

    Args:
        parser: The argument parser to add arguments to

    Returns:
        The same parser with level arguments added
    """
    parser.add_argument(
        "--level",
        type=str,
        default=None,
        help="Difficulty level to filter by. Single level (e.g., '5') or range (e.g., '1-9')",
    )

    return parser


def parse_level_arg(level_str: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """Parse level argument into min/max values.

    Args:
        level_str: Level argument string (e.g., "5" or "1-9")

    Returns:
        Tuple of (min_level, max_level). For single level, both are the same.
        Returns (None, None) if level_str is None.

    Raises:
        ValueError: If level string is invalid
    """
    if level_str is None:
        return None, None

    if "-" in level_str:
        parts = level_str.split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid level range: {level_str}. Use format like '1-9'")
        try:
            min_level = int(parts[0])
            max_level = int(parts[1])
        except ValueError:
            raise ValueError(f"Invalid level range: {level_str}. Levels must be integers.")
        if min_level > max_level:
            raise ValueError(f"Invalid level range: {level_str}. Min level must be <= max level.")
        return min_level, max_level
    else:
        try:
            level = int(level_str)
        except ValueError:
            raise ValueError(f"Invalid level: {level_str}. Must be an integer or range.")
        return level, level


def add_pos_type_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add part-of-speech type filtering arguments.

    Args:
        parser: The argument parser to add arguments to

    Returns:
        The same parser with POS type arguments added
    """
    parser.add_argument(
        "--pos-type",
        type=str,
        default=None,
        help="Part of speech type to filter by (e.g., 'noun', 'verb', 'adjective')",
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

        count: int = query.count()

        if hasattr(args, "sample_rate") and args.sample_rate < 1.0:
            count = int(count * args.sample_rate)

        return count * multiplier
    finally:
        session.close()


def get_data_source_config(args: Any, default_model: Optional[str] = None) -> "DataSourceConfig":
    """Create DataSourceConfig from parsed arguments.

    Args:
        args: Parsed arguments with backend, cache, and LLM-related attributes
        default_model: Default LLM model if not specified in args

    Returns:
        DataSourceConfig instance (always returns a valid config)
    """
    from storage.backend.config import BackendType, DataSourceConfig

    # Determine backend type and paths
    backend_type = None
    sqlite_path = None
    jsonl_data_dir = None
    postgres_url = None

    persona_name = getattr(args, "persona", None)

    # The manual backend flags are only honored with --persona custom, so that
    # --persona stays the single way to select a database.
    manual_flags = []
    if getattr(args, "postgres", False):
        manual_flags.append("--postgres")
    if getattr(args, "backend", None):
        manual_flags.append("--backend")
    if getattr(args, "data_dir", None):
        manual_flags.append("--data-dir")
    if manual_flags and persona_name != CUSTOM_PERSONA:
        print(f"Error: {', '.join(manual_flags)} requires --persona custom")
        sys.exit(1)

    if persona_name == CUSTOM_PERSONA:
        # Manual backend selection: --postgres wins, then --backend, then
        # --db-path (implies SQLite), then the default SQLite database.
        if getattr(args, "postgres", False):
            backend_type = BackendType.POSTGRES
            postgres_url = DataSourceConfig.build_postgres_url()
        elif getattr(args, "backend", None):
            if args.backend == "sqlite":
                backend_type = BackendType.SQLITE
                sqlite_path = (
                    args.db_path
                    if hasattr(args, "db_path") and args.db_path
                    else constants.WORDFREQ_DB_PATH
                )
            elif args.backend == "jsonl":
                if not getattr(args, "data_dir", None):
                    print("Error: --data-dir is required when using --backend jsonl")
                    sys.exit(1)
                backend_type = BackendType.JSONL
                jsonl_data_dir = getattr(args, "data_dir", None)
            elif args.backend == "postgres":
                backend_type = BackendType.POSTGRES
                postgres_url = DataSourceConfig.build_postgres_url()
        elif hasattr(args, "db_path") and args.db_path:
            backend_type = BackendType.SQLITE
            sqlite_path = args.db_path
    elif persona_name:
        # A persona names the main database directly. Only the persona's main
        # database applies: agents do not use its concepts, worker, or UI
        # settings.
        from barsukas.personas import get_persona

        persona = get_persona(persona_name)
        if persona.use_postgres:
            backend_type = BackendType.POSTGRES
            postgres_url = DataSourceConfig.build_postgres_url()
        elif persona.use_jsonl:
            backend_type = BackendType.JSONL
            jsonl_data_dir = str(
                Path(__file__).parent.parent.parent.parent / (persona.jsonl_data_dir or "")
            )
        else:
            backend_type = BackendType.SQLITE
            sqlite_path = (
                args.db_path
                if hasattr(args, "db_path") and args.db_path
                else constants.WORDFREQ_DB_PATH
            )
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
    use_word2vec = args.use_word2vec if hasattr(args, "use_word2vec") else False

    config = DataSourceConfig(
        backend_type=backend_type,
        sqlite_path=sqlite_path,
        jsonl_data_dir=jsonl_data_dir,
        postgres_url=postgres_url,
        barsukas_url=barsukas_url,
        cache_only=cache_only,
        use_word2vec=use_word2vec,
        model=model,
        debug=debug,
    )

    # Declare this as the process's main database. Consumers that cannot take
    # the config directly (no-arg create_session(), the S3 staging prefix)
    # read the declared backend instead of the environment.
    from storage.backend.factory import configure_backend

    configure_backend(config)

    return config


def configure_benchmarks_session_backend(args: Any) -> None:
    """Configure the benchmark datastore backend from the persona.

    The benchmark datastore (model registry, used by UnifiedLLMClient lookups)
    is PostgreSQL for every persona except the fully offline local-sqlite one.
    """
    import benchmarks.datastore.common as datastore_common

    if getattr(args, "persona", None) == PersonaName.LOCAL_SQLITE.value:
        datastore_common.use_sqlite_backend()
