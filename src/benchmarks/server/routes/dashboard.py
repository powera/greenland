#!/usr/bin/python3

"""Dashboard routes - main scoreboard view."""

from datetime import datetime

from flask import Blueprint, g, render_template
from sqlalchemy import func

from benchmarks.datastore.benchmarks import Benchmark, Run, RunDetail
from benchmarks.datastore.common import Model

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


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
    # Get all models
    models = g.db.query(Model).order_by(Model.displayname).all()

    # Get all benchmarks
    benchmarks = g.db.query(Benchmark).order_by(Benchmark.displayname).all()

    # Get highest scoring run for each (benchmark, model) combination
    # Also calculate average eval time
    subquery = (
        g.db.query(
            Run.benchmark_name,
            Run.model_name,
            func.max(Run.normed_score).label("max_score"),
        )
        .group_by(Run.benchmark_name, Run.model_name)
        .subquery()
    )

    # Join to get the actual run IDs and calculate avg eval time
    runs_data = (
        g.db.query(
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

    # Calculate average eval times for each run
    avg_times = {}
    for run_id, bench_name, model_name, score, run_ts in runs_data:
        avg_time = (
            g.db.query(func.avg(RunDetail.eval_msec)).filter(RunDetail.run_id == run_id).scalar()
        )
        avg_times[run_id] = avg_time or 0

    # Build scores dictionary
    scores = {}
    for run_id, bench_name, model_name, score, run_ts in runs_data:
        scores[(bench_name, model_name)] = {
            "run_id": run_id,
            "value": score,
            "color": get_score_color(score),
            "avg_eval_time": avg_times.get(run_id, 0),
            "run_ts": run_ts,
        }

    return render_template(
        "dashboard/index.html",
        models=models,
        benchmarks=benchmarks,
        scores=scores,
        current_time=datetime.now().strftime("%B %d, %Y at %H:%M"),
    )
