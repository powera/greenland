#!/usr/bin/python3
"""Unit tests for the shared benchmark UI summary helpers."""

import pytest

from benchmarks.server.analysis import (
    PriceDiagnostics,
    RunMetrics,
    describe_run_warnings,
    get_score_color,
)


def _metrics(
    *,
    outlier_count: int = 0,
    excluded_question_count: int = 0,
    has_mismatch: bool = False,
) -> RunMetrics:
    """Build a RunMetrics carrying only the fields the warning text reads."""
    return RunMetrics(
        effective_score=100,
        included_question_count=10,
        excluded_question_count=excluded_question_count,
        correct_count=10,
        incorrect_count=0,
        avg_time_msec=100.0,
        median_time_msec=100.0,
        outlier_count=outlier_count,
        total_cost_usd=0.001,
        total_tokens=100,
        price_diagnostics=PriceDiagnostics(
            status="warning" if has_mismatch else "ok",
            label="",
            message="",
            estimated_total_cost_usd=0.001,
            stored_total_cost_usd=0.001,
            coverage="verified",
            has_mismatch=has_mismatch,
        ),
    )


def test_no_warnings_when_run_is_clean() -> None:
    assert describe_run_warnings(_metrics()) == []


def test_outlier_count_is_pluralized() -> None:
    assert describe_run_warnings(_metrics(outlier_count=1)) == ["1 latency outlier"]
    assert describe_run_warnings(_metrics(outlier_count=3)) == ["3 latency outliers"]


def test_cost_mismatch_alone() -> None:
    assert describe_run_warnings(_metrics(has_mismatch=True)) == ["cost warning"]


def test_all_three_warnings_keep_a_stable_order() -> None:
    warnings = describe_run_warnings(
        _metrics(outlier_count=2, excluded_question_count=4, has_mismatch=True)
    )
    assert warnings == ["2 latency outliers", "cost warning", "4 excluded Q"]


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, "#1b5e20"),
        (90, "#1b5e20"),
        (89, "#4caf50"),
        (75, "#4caf50"),
        (50, "#ff9800"),
        (25, "#f44336"),
        (0, "#b71c1c"),
    ],
)
def test_score_color_thresholds(score: int, expected: str) -> None:
    """These thresholds are mirrored in static/js/dashboard.js as SCORE_COLORS."""
    assert get_score_color(score) == expected
