#!/usr/bin/python3

"""Shared analysis helpers for benchmark dashboard and run pages."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Optional

from util.telemetry import CostConfig

LATENCY_OUTLIER_MSEC = 15_000
LATENCY_OUTLIER_RATIO = 8.0


@dataclass(frozen=True)
class PriceDiagnostics:
    """Summary of stored-vs-estimated cost consistency for a run."""

    status: str
    label: str
    message: str
    estimated_total_cost_usd: Optional[float]
    stored_total_cost_usd: float
    coverage: str
    has_mismatch: bool


@dataclass(frozen=True)
class RunMetrics:
    """Derived metrics used throughout the benchmark web UI."""

    effective_score: int
    included_question_count: int
    excluded_question_count: int
    correct_count: int
    incorrect_count: int
    avg_time_msec: float
    median_time_msec: float
    outlier_count: int
    total_cost_usd: float
    total_tokens: int
    price_diagnostics: PriceDiagnostics


def get_score_color(score: float) -> str:
    """Return the background colour used for a 0-100 score badge.

    The same thresholds are mirrored in server/static/js/dashboard.js as
    SCORE_COLORS; keep the two in sync.
    """
    if score >= 90:
        return "#1b5e20"  # Excellent - dark green
    elif score >= 75:
        return "#4caf50"  # Good - green
    elif score >= 50:
        return "#ff9800"  # Average - orange
    elif score >= 25:
        return "#f44336"  # Below average - red
    else:
        return "#b71c1c"  # Poor - dark red


def describe_run_warnings(metrics: RunMetrics) -> list[str]:
    """Return short human-readable caveats about a run's aggregate metrics.

    Used by the dashboard grid, the benchmark leaderboard, and the model page so
    the same caveats are worded identically everywhere.
    """
    warnings: list[str] = []
    if metrics.outlier_count:
        plural = "s" if metrics.outlier_count != 1 else ""
        warnings.append(f"{metrics.outlier_count} latency outlier{plural}")
    if metrics.price_diagnostics.has_mismatch:
        warnings.append("cost warning")
    if metrics.excluded_question_count:
        warnings.append(f"{metrics.excluded_question_count} excluded Q")
    return warnings


def correctness_threshold(benchmark_name: str) -> int:
    """Return the minimum score treated as correct for a benchmark."""
    return 70 if benchmark_name == "0062_sentence_decomposition" else 100


def analyze_run_details(
    benchmark_name: str,
    details: list[dict[str, Any]],
    *,
    model_path: Optional[str],
    model_type: Optional[str],
) -> RunMetrics:
    """Decorate run details and calculate aggregate metrics for UI display."""
    threshold = correctness_threshold(benchmark_name)
    included_details = [detail for detail in details if not detail.get("is_question_excluded")]
    included_latencies = [
        int(detail["eval_msec"])
        for detail in included_details
        if isinstance(detail.get("eval_msec"), (int, float)) and detail.get("eval_msec") is not None
    ]
    baseline_median = float(median(included_latencies)) if included_latencies else 0.0

    corrected_included: list[dict[str, Any]] = []
    outlier_count = 0
    for detail in details:
        score_value = int(detail.get("score") or 0)
        is_correct = score_value >= threshold
        latency_value = detail.get("eval_msec")
        is_question_excluded = bool(detail.get("is_question_excluded"))
        latency_outlier = (
            not is_question_excluded
            and not is_correct
            and isinstance(latency_value, (int, float))
            and latency_value >= LATENCY_OUTLIER_MSEC
            and (
                baseline_median <= 0
                or latency_value >= baseline_median * LATENCY_OUTLIER_RATIO
                or latency_value >= 30_000
            )
        )

        detail["is_correct"] = is_correct
        detail["is_latency_outlier"] = latency_outlier
        detail["excluded_from_latency"] = latency_outlier or is_question_excluded

        if latency_outlier:
            outlier_count += 1

        if not is_question_excluded:
            corrected_included.append(detail)

    included_count = len(corrected_included)
    correct_count = sum(1 for detail in corrected_included if detail["is_correct"])
    incorrect_count = included_count - correct_count
    effective_score = round((correct_count / included_count) * 100) if included_count else 0

    displayed_latencies = [
        float(detail["eval_msec"])
        for detail in corrected_included
        if not detail.get("excluded_from_latency")
        and isinstance(detail.get("eval_msec"), (int, float))
        and detail.get("eval_msec") is not None
    ]
    avg_time = sum(displayed_latencies) / len(displayed_latencies) if displayed_latencies else 0.0
    median_time = float(median(displayed_latencies)) if displayed_latencies else 0.0

    total_cost = sum((detail.get("cost_usd") or 0.0) for detail in corrected_included)
    total_tokens = sum((detail.get("tokens_used") or 0) for detail in corrected_included)
    pricing = detect_price_issues(
        corrected_included,
        model_path=model_path,
        model_type=model_type,
    )

    return RunMetrics(
        effective_score=effective_score,
        included_question_count=included_count,
        excluded_question_count=len(details) - included_count,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        avg_time_msec=avg_time,
        median_time_msec=median_time,
        outlier_count=outlier_count,
        total_cost_usd=total_cost,
        total_tokens=total_tokens,
        price_diagnostics=pricing,
    )


def detect_price_issues(
    details: Iterable[dict[str, Any]],
    *,
    model_path: Optional[str],
    model_type: Optional[str],
) -> PriceDiagnostics:
    """Compare stored prices with current pricing rules when enough data exists."""
    detail_list = list(details)
    stored_total_cost = float(sum((detail.get("cost_usd") or 0.0) for detail in detail_list))
    if not detail_list:
        return PriceDiagnostics(
            status="ok",
            label="No included questions",
            message="No active questions remain after exclusions.",
            estimated_total_cost_usd=0.0,
            stored_total_cost_usd=stored_total_cost,
            coverage="none",
            has_mismatch=False,
        )

    observed_ratios = [
        (detail["tokens_in"] / max(detail["tokens_in"] + detail["tokens_out"], 1))
        for detail in detail_list
        if isinstance(detail.get("tokens_in"), int) and isinstance(detail.get("tokens_out"), int)
    ]
    inferred_input_ratio = median(observed_ratios) if observed_ratios else 0.75

    estimated_total_cost = 0.0
    verified_count = 0
    estimated_count = 0
    computable_count = 0
    for detail in detail_list:
        estimate = estimate_detail_cost(
            detail,
            model_path=model_path,
            model_type=model_type,
            inferred_input_ratio=inferred_input_ratio,
        )
        if estimate is None:
            continue
        computable_count += 1
        estimated_total_cost += estimate
        if isinstance(detail.get("tokens_in"), int) and isinstance(detail.get("tokens_out"), int):
            verified_count += 1
        elif model_type != "remote":
            verified_count += 1
        else:
            estimated_count += 1

    if computable_count == 0:
        return PriceDiagnostics(
            status="unknown",
            label="Cost unverifiable",
            message="Not enough usage data is available to re-estimate this run's cost.",
            estimated_total_cost_usd=None,
            stored_total_cost_usd=stored_total_cost,
            coverage="none",
            has_mismatch=False,
        )

    difference = abs(stored_total_cost - estimated_total_cost)
    larger_cost = max(abs(stored_total_cost), abs(estimated_total_cost), 1e-9)
    relative_difference = difference / larger_cost
    has_mismatch = difference >= 0.00005 and relative_difference >= 0.5

    coverage = "verified" if estimated_count == 0 else "estimated"
    if has_mismatch:
        label = "Suspicious cost data"
        message = "Stored run cost differs noticeably from the current pricing estimate" + (
            " (estimated token split)." if coverage == "estimated" else "."
        )
        status = "warning"
    else:
        label = "Cost looks consistent"
        message = (
            "Stored run cost is consistent with the current pricing rules."
            if coverage == "verified"
            else "Stored run cost is broadly consistent with an estimated token split."
        )
        status = "ok"

    return PriceDiagnostics(
        status=status,
        label=label,
        message=message,
        estimated_total_cost_usd=estimated_total_cost,
        stored_total_cost_usd=stored_total_cost,
        coverage=coverage,
        has_mismatch=has_mismatch,
    )


def estimate_detail_cost(
    detail: dict[str, Any],
    *,
    model_path: Optional[str],
    model_type: Optional[str],
    inferred_input_ratio: float,
) -> Optional[float]:
    """Estimate cost for a single question using current pricing heuristics."""
    model_identifier = model_path or ""
    if model_type == "remote":
        tokens_in = detail.get("tokens_in")
        tokens_out = detail.get("tokens_out")
        if isinstance(tokens_in, int) and isinstance(tokens_out, int):
            return CostConfig.estimate_cost(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                model=model_identifier,
            )

        tokens_used = detail.get("tokens_used")
        if isinstance(tokens_used, int):
            estimated_input = round(tokens_used * inferred_input_ratio)
            estimated_output = max(tokens_used - estimated_input, 0)
            return CostConfig.estimate_cost(
                tokens_in=estimated_input,
                tokens_out=estimated_output,
                model=model_identifier,
            )
        return None

    eval_msec = detail.get("eval_msec")
    if isinstance(eval_msec, (int, float)):
        return CostConfig.estimate_cost(
            compute_ms=float(eval_msec),
            model=model_identifier,
        )
    return None
