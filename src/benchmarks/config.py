"""Configuration for benchmark system.

This module provides configuration management for the benchmark subsystem,
which is separate from the main linguistics/wordfreq database.
"""

import os
from pathlib import Path
from typing import Optional

from benchmarks.benchmark_constants import (
    BENCHMARKS_DB_PATH,
    BENCHMARKS_POSTGRES_SCHEMA,
    DEFAULT_BENCHMARK_MODEL,
)


class BenchmarkConfig:
    """Configuration for benchmark operations.

    This handles benchmark-specific configuration including database path,
    model selection, and debug settings. Unlike DataSourceConfig, this is
    simpler and focused solely on benchmarks (no JSONL backend, no cache).

    Supports both SQLite (local file) and PostgreSQL (Supabase) backends.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        postgres_url: Optional[str] = None,
        model: Optional[str] = None,
        debug: bool = False,
    ):
        """Initialize benchmark configuration.

        Exactly one of db_path or postgres_url should be provided; db_path
        takes precedence if both are given.

        Args:
            db_path: Path to benchmarks SQLite database (default: benchmark_constants.BENCHMARKS_DB_PATH)
            postgres_url: PostgreSQL connection URL for Supabase backend
            model: LLM model to use for running benchmarks (e.g., "gpt-4o-mini", "claude-sonnet-4")
            debug: Enable debug logging
        """
        self.db_path = db_path or str(BENCHMARKS_DB_PATH)
        self.postgres_url = postgres_url
        self.model = model or DEFAULT_BENCHMARK_MODEL
        self.debug = debug

    @classmethod
    def from_env(cls) -> "BenchmarkConfig":
        """Create configuration from environment variables.

        Environment variables:
            BENCH_STORAGE_BACKEND: "sqlite" or "postgres" (default: "sqlite")
            BENCHMARKS_DB_PATH: Path to benchmarks database (optional, sqlite only)
            BENCH_POSTGRES_URL: Full PostgreSQL URL (optional; built from key file if absent)
            BENCHMARK_MODEL: Default LLM model to use (optional)
            DEBUG: "true" or "false" (default: "false")

        Returns:
            BenchmarkConfig instance
        """
        backend = os.environ.get("BENCH_STORAGE_BACKEND", "sqlite").lower()
        db_path = os.environ.get("BENCHMARKS_DB_PATH")
        model = os.environ.get("BENCHMARK_MODEL")
        debug = os.environ.get("DEBUG", "false").lower() == "true"

        postgres_url: Optional[str] = None
        if backend == "postgres":
            postgres_url = os.environ.get("BENCH_POSTGRES_URL")
            if postgres_url:
                postgres_url = cls.normalize_postgres_url(postgres_url)
            else:
                postgres_url = cls.build_postgres_url()

        return cls(
            db_path=db_path,
            postgres_url=postgres_url,
            model=model,
            debug=debug,
        )

    @classmethod
    def build_postgres_url(cls) -> str:
        """Build PostgreSQL URL by combining template with password from key file.

        Uses the same Supabase project as the main linguistics database, but
        sets the schema to BENCHMARKS_POSTGRES_SCHEMA via the search_path option.

        Returns:
            Complete PostgreSQL connection URL with schema configured

        Raises:
            ValueError: If password file not found or template invalid
        """
        from storage.backend.config import DataSourceConfig

        base_url = DataSourceConfig.build_postgres_url()

        # Replace any inherited schema/path settings with benchmarks.
        return cls.normalize_postgres_url(base_url)

    @classmethod
    def normalize_postgres_url(cls, postgres_url: str) -> str:
        """Ensure a PostgreSQL URL targets the benchmarks schema.

        This is applied to auto-built URLs and user-provided BENCH_POSTGRES_URL
        values so pooled/direct Supabase URLs are handled consistently.

        Args:
            postgres_url: Any PostgreSQL connection URL

        Returns:
            URL with options=-csearch_path%3Dbenchmarks present
        """
        schema = BENCHMARKS_POSTGRES_SCHEMA
        if "search_path" in postgres_url:
            # Strip the existing search_path option and replace with ours.
            # The option is appended as &options=... or ?options=...
            return _replace_search_path(postgres_url, schema)

        sep = "&" if "?" in postgres_url else "?"
        return f"{postgres_url}{sep}options=-csearch_path%3D{schema}"

    @property
    def using_postgres(self) -> bool:
        """Return True when the PostgreSQL backend is active."""
        return self.postgres_url is not None

    def __repr__(self) -> str:
        """String representation of config."""
        if self.using_postgres:
            url = self.postgres_url or ""
            if "@" in url:
                prefix, rest = url.split("@", 1)
                display_url = f"postgresql://***@{rest}"
            else:
                display_url = url
            parts = [f"postgres_url={display_url}"]
        else:
            parts = [f"db_path={self.db_path}"]

        parts.append(f"model={self.model}")
        if self.debug:
            parts.append("debug=True")

        return f"BenchmarkConfig({', '.join(parts)})"


def _replace_search_path(url: str, new_schema: str) -> str:
    """Replace the search_path value in a PostgreSQL connection URL.

    Args:
        url: PostgreSQL URL that already contains a search_path option
        new_schema: New schema name to use

    Returns:
        URL with the search_path replaced
    """
    import re

    # Match the encoded search_path option: options=-csearch_path%3D<schema>
    pattern = r"(options=-csearch_path%3D)[^&]+"
    replacement = rf"\g<1>{new_schema}"
    new_url = re.sub(pattern, replacement, url)
    if new_url == url:
        # Pattern not matched; append as new option
        sep = "&" if "?" in url else "?"
        new_url = f"{url}{sep}options=-csearch_path%3D{new_schema}"
    return new_url
