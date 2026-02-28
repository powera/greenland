#!/usr/bin/python3

"""Dashboard routes - main scoreboard view."""

from datetime import datetime

from flask import Blueprint, g, render_template
from sqlalchemy import case, func

from benchmarks.datastore.benchmarks import Benchmark, Run, RunDetail
from benchmarks.datastore.common import Model
from benchmarks.tiers import BENCHMARK_TIERS, get_benchmark_tier, model_can_run_benchmark

bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard",
    template_folder="../templates",
    static_folder="../static",
)


def get_score_color(score):
    """Get color for score visualization."""
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


@bp.route("/")
def index():
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

    # Get highest scoring run for each (benchmark, model) combination
    # Also calculate average eval time and average cost per question.
    subquery = (
        g.bench_db.query(
            Run.benchmark_name,
            Run.model_name,
            func.max(Run.normed_score).label("max_score"),
        )
        .group_by(Run.benchmark_name, Run.model_name)
        .subquery()
    )

    # Join to get the actual run IDs and calculate averages for the run details
    # in the same query. This avoids per-run aggregate queries, which are
    # expensive with high DB latency.
    runs_data = (
        g.bench_db.query(
            Run.run_id,
            Run.benchmark_name,
            Run.model_name,
            Run.normed_score,
            Run.run_ts,
            func.avg(RunDetail.eval_msec).label("avg_eval_time"),
            func.avg(RunDetail.cost_usd).label("avg_cost_usd"),
        )
        .join(
            subquery,
            (Run.benchmark_name == subquery.c.benchmark_name)
            & (Run.model_name == subquery.c.model_name)
            & (Run.normed_score == subquery.c.max_score),
        )
        .outerjoin(RunDetail, RunDetail.run_id == Run.run_id)
        .group_by(
            Run.run_id,
            Run.benchmark_name,
            Run.model_name,
            Run.normed_score,
            Run.run_ts,
        )
        .all()
    )

    # Build scores dictionary
    scores = {}
    for run_id, bench_name, model_name, score, run_ts, avg_eval_time, avg_cost_usd in runs_data:
        scores[(bench_name, model_name)] = {
            "run_id": run_id,
            "value": score,
            "color": get_score_color(score),
            "avg_eval_time": avg_eval_time or 0,
            "avg_cost_usd": avg_cost_usd or 0,
            "run_ts": run_ts,
        }

    categories = sorted({b.category for b in benchmarks if b.category})
    eligibility = {
        (benchmark.codename, model.codename): model_can_run_benchmark(model, benchmark.codename)
        for benchmark in benchmarks
        for model in models
    }
    benchmark_tiers = {
        benchmark.codename: get_benchmark_tier(benchmark.codename) for benchmark in benchmarks
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
        current_time=datetime.now().strftime("%B %d, %Y at %H:%M"),
    )
