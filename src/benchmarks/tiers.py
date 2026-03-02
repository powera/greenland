#!/usr/bin/python3

"""Benchmark tier/grouping helpers.

Tier 1 contains screening benchmarks that weak models can run quickly.
Tier 2 contains the full benchmark catalog.
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkTier:
    """Human-readable benchmark tier metadata."""

    level: int
    label: str
    short_label: str
    description: str


BENCHMARK_TIERS: dict[int, BenchmarkTier] = {
    1: BenchmarkTier(
        level=1,
        label="Tier 1 (Screening)",
        short_label="T1",
        description="Simple baseline tasks (0010–0029 and translation sanity checks 0101–0109).",
    ),
    2: BenchmarkTier(
        level=2,
        label="Tier 2 (Full)",
        short_label="T2+",
        description="Full benchmark catalog.",
    ),
    3: BenchmarkTier(
        level=3,
        label="Tier 3 (Advanced)",
        short_label="T3",
        description="Reserved for future advanced benchmarks (opt-in by model).",
    ),
}

_SCREENING_TRANSLATION_CODES = {f"{value:04d}" for value in range(101, 110)}


def get_benchmark_tier(benchmark_code: str) -> int:
    """Return the tier level for a benchmark code."""
    match = re.match(r"^(\d{4})", benchmark_code)
    if not match:
        return 2

    numeric_code = int(match.group(1))
    if 10 <= numeric_code <= 29:
        return 1

    if match.group(1) in _SCREENING_TRANSLATION_CODES:
        return 1

    return 2


def get_model_max_tier(model: Any) -> int:
    """Return the max tier a model should run."""
    max_tier_value = getattr(model, "max_benchmark_tier", None)
    if isinstance(max_tier_value, int) and max_tier_value >= 1:
        return max_tier_value
    return 2


def model_can_run_benchmark(model: Any, benchmark_code: str) -> bool:
    """Return whether a model is eligible for a benchmark based on tiers."""
    return get_model_max_tier(model) >= get_benchmark_tier(benchmark_code)


def get_tier_label(level: int) -> str:
    """Return a human label for a tier level."""
    tier = BENCHMARK_TIERS.get(level)
    if tier is not None:
        return tier.label
    return f"Tier {level}"
