#!/usr/bin/python3

"""Configuration for Benchmark Server web interface."""

import os
from ipaddress import ip_network
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

    # Benchmark runner controls
    BENCHMARK_RUNNER_ENABLED = os.environ.get("BENCH_SERVER_RUNNER_ENABLED", "true").lower() == "true"
    BENCHMARK_RUNNER_ALLOWED_CIDRS = tuple(
        ip_network(cidr.strip())
        for cidr in os.environ.get(
            "BENCH_SERVER_RUNNER_ALLOWED_CIDRS",
            "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10",
        ).split(",")
        if cidr.strip()
    )
    BENCHMARK_RUNNER_BLOCK_PROXIED_REQUESTS = (
        os.environ.get("BENCH_SERVER_RUNNER_BLOCK_PROXIED_REQUESTS", "true").lower() == "true"
    )
