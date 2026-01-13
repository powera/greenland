"""Configuration for benchmark system.

This module provides configuration management for the benchmark subsystem,
which is separate from the main linguistics/wordfreq database.
"""

import os
from pathlib import Path
from typing import Optional

from benchmarks.benchmark_constants import (
    BENCHMARKS_DB_PATH,
    DEFAULT_BENCHMARK_MODEL,
)


class BenchmarkConfig:
    """Configuration for benchmark operations.

    This handles benchmark-specific configuration including database path,
    model selection, and debug settings. Unlike DataSourceConfig, this is
    simpler and focused solely on benchmarks (no JSONL backend, no cache).
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        model: Optional[str] = None,
        debug: bool = False,
    ):
        """Initialize benchmark configuration.

        Args:
            db_path: Path to benchmarks SQLite database (default: benchmark_constants.BENCHMARKS_DB_PATH)
            model: LLM model to use for running benchmarks (e.g., "gpt-4o-mini", "claude-sonnet-4")
            debug: Enable debug logging
        """
        self.db_path = db_path or str(BENCHMARKS_DB_PATH)
        self.model = model or DEFAULT_BENCHMARK_MODEL
        self.debug = debug

    @classmethod
    def from_env(cls) -> "BenchmarkConfig":
        """Create configuration from environment variables.

        Environment variables:
            BENCHMARKS_DB_PATH: Path to benchmarks database (optional)
            BENCHMARK_MODEL: Default LLM model to use (optional)
            DEBUG: "true" or "false" (default: "false")

        Returns:
            BenchmarkConfig instance
        """
        db_path = os.environ.get("BENCHMARKS_DB_PATH")
        model = os.environ.get("BENCHMARK_MODEL")
        debug = os.environ.get("DEBUG", "false").lower() == "true"

        return cls(
            db_path=db_path,
            model=model,
            debug=debug,
        )

    def __repr__(self) -> str:
        """String representation of config."""
        parts = [
            f"db_path={self.db_path}",
            f"model={self.model}",
        ]
        if self.debug:
            parts.append("debug=True")

        return f"BenchmarkConfig({', '.join(parts)})"
