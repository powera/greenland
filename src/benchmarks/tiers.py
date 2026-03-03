#!/usr/bin/python3

"""Benchmark tier/grouping helpers.

Tier 1 contains screening benchmarks that weak models can run quickly.
Tier 2 contains the main operational benchmark suites.
Tier 3 contains heavier/advanced benchmarks.
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
        label="Tier 2 (Core)",
        short_label="T2",
        description="Core benchmark suites used for regular model evaluation.",
    ),
    3: BenchmarkTier(
        level=3,
        label="Tier 3 (Advanced)",
        short_label="T3",
        description="Advanced and more expensive benchmarks (opt-in by model).",
    ),
}

_SCREENING_TRANSLATION_CODES = {f"{value:04d}" for value in range(101, 110)}
_CORE_BENCHMARK_CODES = (
    {f"{value:04d}" for value in range(31, 34)}
    | {f"{value:04d}" for value in range(151, 156)}
    | {f"{value:04d}" for value in range(301, 306)}
)
_ADVANCED_BENCHMARK_CODES = {
    "0061",
    "0062",
} | {f"{value:04d}" for value in range(111, 151)}


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

    if match.group(1) in _CORE_BENCHMARK_CODES:
        return 2

    if match.group(1) in _ADVANCED_BENCHMARK_CODES:
        return 3

    return 2


def get_model_max_tier(model: Any) -> int:
    """Deprecated alias for get_model_capability_level."""
    return get_model_capability_level(model)


def get_model_capability_level(model: Any) -> int:
    """Return the maximum benchmark tier a model can run."""
    max_tier_value = getattr(model, "max_benchmark_tier", None)
    if isinstance(max_tier_value, int) and max_tier_value >= 1:
        return max_tier_value
    return 2


def model_can_run_benchmark(model: Any, benchmark_code: str) -> bool:
    """Return whether a model is eligible for a benchmark based on tiers."""
    return get_model_capability_level(model) >= get_benchmark_tier(benchmark_code)


def get_tier_label(level: int) -> str:
    """Return a human label for a tier level."""
    tier = BENCHMARK_TIERS.get(level)
    if tier is not None:
        return tier.label
    return f"Tier {level}"


def get_model_capability_label(level: int) -> str:
    """Return a human label for model capability levels."""
    return f"Level {level}"
