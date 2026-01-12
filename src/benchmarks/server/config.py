#!/usr/bin/python3

"""Configuration for Benchmark Server web interface."""

import os
from pathlib import Path


class Config:
    """Application configuration."""

    # Flask settings
    SECRET_KEY = os.environ.get("BENCH_SERVER_SECRET_KEY", "dev-secret-key-change-in-production")

    # Server settings
    HOST = "127.0.0.1"  # Localhost only for security
    PORT = int(os.environ.get("BENCH_SERVER_PORT", 5556))
    DEBUG = os.environ.get("BENCH_SERVER_DEBUG", "False").lower() == "true"

    # Database settings
    BASE_DIR = Path(__file__).parent.parent.parent  # repo root
    DEFAULT_DB_PATH = BASE_DIR / "src" / "benchmarks" / "schema" / "benchmarks.db"
    DB_PATH = os.environ.get("BENCH_SERVER_DB_PATH", str(DEFAULT_DB_PATH))

    # Pagination
    ITEMS_PER_PAGE = 50

    # Access control
    READONLY = False  # Can be overridden at runtime
