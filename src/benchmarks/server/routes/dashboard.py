#!/usr/bin/python3

"""Dashboard routes - main scoreboard view."""

from datetime import datetime
from itertools import groupby
from statistics import median
from typing import Any, Optional

from flask import Blueprint, g, render_template
from sqlalchemy import case

from benchmarks.datastore.benchmarks import Benchmark, Question, Run, RunDetail
from benchmarks.datastore.common import Model
from benchmarks.server.analysis import (
    analyze_run_details,
    describe_run_warnings,
    get_score_color,
)
from benchmarks.tiers import BENCHMARK_TIERS, get_benchmark_tier, model_can_run_benchmark

__all__ = ["bp", "get_score_color", "index", "summarize_cells"]

bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard",
    template_folder="../templates",
    static_folder="../static",
)


def summarize_cells(cells: list[dict[str, Any]]) -> Optional[dict[str, float]]:
    """Aggregate a set of grid cells into mean score, median latency, mean cost.

    Returns None when there is nothing to summarize, so the template can render a
    placeholder rather than a misleading zero.
    """
    if not cells:
        return None
    return {
        "count": len(cells),
        "score": sum(cell["score"] for cell in cells) / len(cells),
        "latency_msec": float(median([cell["latency_msec"] for cell in cells])),
        "cost_micro_usd": sum(cell["cost_micro_usd"] for cell in cells) / len(cells),
    }


@bp.route("/")
def index() -> str:
    """Display the main benchmark dashboard with model-benchmark matrix."""
    # Get models with at least one run, ordered with remote models first.
    models = (
        g.bench_db.query(Model)
        .filter(g.bench_db.query(Run.run_id).filter(Run.model_name == Model.codename).exists())
        .order_by(
            case((Model.model_type == "remote", 0), else_=1),
            Model.displayname,
        )
        .all()
    )

    # Get all benchmarks
    benchmarks = g.bench_db.query(Benchmark).order_by(Benchmark.codename).all()

    run_rows = (
        g.bench_db.query(
            Run,
            RunDetail,
            Model,
            Question,
        )
        .join(Model, Run.model_name == Model.codename)
        .outerjoin(RunDetail, RunDetail.run_id == Run.run_id)
        .outerjoin(Question, RunDetail.question_id == Question.question_id)
        .order_by(Run.benchmark_name, Run.model_name, Run.run_id, Run.run_ts)
        .all()
    )

    scores = {}
    for (_benchmark_name, _model_name), grouped_rows in groupby(
        run_rows,
        key=lambda row: (row[0].benchmark_name, row[0].model_name),
    ):
        best_run_data = None
        for _run_id, run_details_iter in groupby(grouped_rows, key=lambda row: row[0].run_id):
            detail_records = []
            run = None
            model_record = None
            for current_run, detail, model, question in run_details_iter:
                run = current_run
                model_record = model
                if detail is None:
                    continue
                detail_records.append(
                    {
                        "question_id": detail.question_id,
                        "score": detail.score,
                        "eval_msec": detail.eval_msec,
                        "cost_usd": detail.cost_usd,
                        "tokens_used": detail.tokens_used,
                        "tokens_in": detail.tokens_in,
                        "tokens_out": detail.tokens_out,
                        "is_question_excluded": bool(question.is_excluded) if question else False,
                    }
                )

            if run is None:
                continue

            metrics = analyze_run_details(
                run.benchmark_name,
                detail_records,
                model_path=model_record.model_path if model_record else None,
                model_type=model_record.model_type if model_record else None,
            )
            avg_cost_usd = (
                metrics.total_cost_usd / metrics.included_question_count
                if metrics.included_question_count
                else 0.0
            )
            candidate = {
                "run_id": run.run_id,
                "value": metrics.effective_score,
                "score": metrics.effective_score,
                "color": get_score_color(metrics.effective_score),
                "median_eval_time": metrics.median_time_msec,
                "latency_msec": metrics.median_time_msec,
                "avg_cost_usd": avg_cost_usd,
                "cost_micro_usd": avg_cost_usd * 1_000_000,
                "run_ts": run.run_ts,
                "outlier_count": metrics.outlier_count,
                "excluded_question_count": metrics.excluded_question_count,
                "price_diagnostics": metrics.price_diagnostics,
                "warnings": describe_run_warnings(metrics),
            }
            if best_run_data is None or (
                candidate["value"],
                candidate["run_ts"],
                candidate["run_id"],
            ) > (
                best_run_data["value"],
                best_run_data["run_ts"],
                best_run_data["run_id"],
            ):
                best_run_data = candidate

        if best_run_data is not None:
            scores[(_benchmark_name, _model_name)] = best_run_data

    categories = sorted({b.category for b in benchmarks if b.category})
    eligibility = {
        (benchmark.codename, model.codename): model_can_run_benchmark(model, benchmark.codename)
        for benchmark in benchmarks
        for model in models
    }
    benchmark_tiers = {
        benchmark.codename: get_benchmark_tier(benchmark.codename) for benchmark in benchmarks
    }

    # Server-rendered summaries cover every model / benchmark; the client
    # recomputes them for the visible subset whenever filters change.
    model_summaries = {
        model.codename: summarize_cells(
            [cell for (_, model_code), cell in scores.items() if model_code == model.codename]
        )
        for model in models
    }
    benchmark_summaries = {
        benchmark.codename: summarize_cells(
            [
                cell
                for (benchmark_code, _), cell in scores.items()
                if benchmark_code == benchmark.codename
            ]
        )
        for benchmark in benchmarks
    }

    return render_template(
        "dashboard/index.html",
        models=models,
        benchmarks=benchmarks,
        scores=scores,
        eligibility=eligibility,
        benchmark_tiers=benchmark_tiers,
        tier_definitions=BENCHMARK_TIERS,
        categories=categories,
        model_summaries=model_summaries,
        benchmark_summaries=benchmark_summaries,
        current_time=datetime.now().strftime("%B %d, %Y at %H:%M"),
    )
