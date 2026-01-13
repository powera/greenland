#!/usr/bin/python3

"""Configuration for Benchmark Server web interface."""

import os
from pathlib import Path

from benchmarks.benchmark_constants import (
    BENCHMARKS_DB_PATH,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
)


class Config:
    """Application configuration."""

    # Flask settings
    SECRET_KEY = os.environ.get("BENCH_SERVER_SECRET_KEY", "dev-secret-key-change-in-production")

    # Server settings
    HOST = DEFAULT_SERVER_HOST
    PORT = int(os.environ.get("BENCH_SERVER_PORT", DEFAULT_SERVER_PORT))
    DEBUG = os.environ.get("BENCH_SERVER_DEBUG", "False").lower() == "true"

    # Database settings
    DB_PATH = os.environ.get("BENCH_SERVER_DB_PATH", str(BENCHMARKS_DB_PATH))

    # Pagination
    ITEMS_PER_PAGE = 50

    # Access control
    READONLY = False  # Can be overridden at runtime
