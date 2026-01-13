"""Benchmark-specific constants and paths.

This module defines paths and constants specific to the benchmarks subsystem,
keeping it independent from the wordfreq/linguistics database.
"""

import os
from pathlib import Path

# Get the benchmarks directory
BENCHMARKS_DIR = Path(__file__).parent

# Get the src directory (parent of benchmarks)
SRC_DIR = BENCHMARKS_DIR.parent

# Get the project root
PROJECT_ROOT = SRC_DIR.parent

# Benchmark data directories
# Note: These are kept as Path objects internally, but str() versions are used
# for backwards compatibility with code that expects strings
BENCHMARK_DATA_DIR = BENCHMARKS_DIR
BENCHMARK_SCHEMA_DIR = BENCHMARKS_DIR / "schema"

# Benchmark database path (separate from linguistics.sqlite)
BENCHMARKS_DB_PATH = BENCHMARK_SCHEMA_DIR / "benchmarks.db"

# Individual benchmark test data directories
BENCHMARK_TESTS_DIR = BENCHMARKS_DIR

# Default model for benchmarks
DEFAULT_BENCHMARK_MODEL = "gpt-4o-mini"

# Server defaults
DEFAULT_SERVER_PORT = 5556
DEFAULT_SERVER_HOST = "127.0.0.1"
