#!/usr/bin/python3

"""Dashboard routes - main scoreboard view."""

from datetime import datetime
import json

from flask import Blueprint, g, render_template
from sqlalchemy import case, func

from benchmarks.datastore.benchmarks import Benchmark, Run, RunDetail
from benchmarks.datastore.common import Model

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


def _extract_usage_from_debug(debug_json: str | None) -> tuple[int, int]:
    """Extract token usage from run_detail.debug_json."""
    if not debug_json:
        return 0, 0

    try:
        debug_data = json.loads(debug_json)
    except (TypeError, ValueError):
        return 0, 0

    usage_data = debug_data.get("usage")
    if not isinstance(usage_data, dict):
        return 0, 0

    tokens_in = usage_data.get("tokens_in")
    tokens_out = usage_data.get("tokens_out")
    return (
        tokens_in if isinstance(tokens_in, int) else 0,
        tokens_out if isinstance(tokens_out, int) else 0,
    )


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

    # Join to get the actual run IDs and calculate avg eval time
    runs_data = (
        g.bench_db.query(
            Run.run_id,
            Run.benchmark_name,
            Run.model_name,
            Run.normed_score,
            Run.run_ts,
        )
        .join(
            subquery,
            (Run.benchmark_name == subquery.c.benchmark_name)
            & (Run.model_name == subquery.c.model_name)
            & (Run.normed_score == subquery.c.max_score),
        )
        .all()
    )

    # Calculate average eval times, costs, and token usage for each run
    avg_times = {}
    avg_costs = {}
    avg_tokens = {}
    for run_id, bench_name, model_name, score, run_ts in runs_data:
        run_details = g.bench_db.query(RunDetail).filter(RunDetail.run_id == run_id).all()

        eval_values = [detail.eval_msec for detail in run_details if detail.eval_msec is not None]
        avg_times[run_id] = (sum(eval_values) / len(eval_values)) if eval_values else 0

        cost_values = [detail.cost_usd for detail in run_details if detail.cost_usd is not None]
        avg_costs[run_id] = (sum(cost_values) / len(cost_values)) if cost_values else 0

        usage_pairs = [_extract_usage_from_debug(detail.debug_json) for detail in run_details]
        usage_pairs = [
            (tokens_in, tokens_out)
            for tokens_in, tokens_out in usage_pairs
            if tokens_in or tokens_out
        ]
        if usage_pairs:
            avg_tokens[run_id] = {
                "tokens_in": sum(tokens_in for tokens_in, _ in usage_pairs) / len(usage_pairs),
                "tokens_out": sum(tokens_out for _, tokens_out in usage_pairs) / len(usage_pairs),
            }
        else:
            avg_tokens[run_id] = {"tokens_in": 0, "tokens_out": 0}

    # Build scores dictionary
    scores = {}
    for run_id, bench_name, model_name, score, run_ts in runs_data:
        scores[(bench_name, model_name)] = {
            "run_id": run_id,
            "value": score,
            "color": get_score_color(score),
            "avg_eval_time": avg_times.get(run_id, 0),
            "avg_cost_usd": avg_costs.get(run_id, 0),
            "avg_tokens_in": avg_tokens.get(run_id, {}).get("tokens_in", 0),
            "avg_tokens_out": avg_tokens.get(run_id, {}).get("tokens_out", 0),
            "run_ts": run_ts,
        }

    categories = sorted({b.category for b in benchmarks if b.category})

    return render_template(
        "dashboard/index.html",
        models=models,
        benchmarks=benchmarks,
        scores=scores,
        categories=categories,
        current_time=datetime.now().strftime("%B %d, %Y at %H:%M"),
    )
