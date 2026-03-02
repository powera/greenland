#!/usr/bin/python3

"""Model routes - list and view model details."""

from flask import Blueprint, g, render_template
from sqlalchemy import func

from benchmarks.datastore.benchmarks import Run
from benchmarks.datastore.common import Model
from benchmarks.tiers import get_benchmark_tier, get_tier_label

bp = Blueprint("models", __name__, url_prefix="/models", template_folder="../templates")


def _average_or_none(values: list[float]) -> float | None:
    """Return the arithmetic average for non-empty values."""
    if not values:
        return None
    return round(sum(values) / len(values), 1)


@bp.route("/")
def list_models():
    """List all models with their aggregate statistics."""
    models_query = (
        g.bench_db.query(
            Model,
            func.count(Run.run_id).label("run_count"),
            func.avg(Run.normed_score).label("avg_score"),
            func.max(Run.run_ts).label("last_run"),
        )
        .outerjoin(Run, Model.codename == Run.model_name)
        .group_by(Model.codename)
        .order_by(Model.displayname)
        .all()
    )

    model_benchmark_scores = (
        g.bench_db.query(
            Run.model_name,
            Run.benchmark_name,
            func.avg(Run.normed_score).label("benchmark_avg_score"),
        )
        .group_by(Run.model_name, Run.benchmark_name)
        .all()
    )

    tier_scores_by_model: dict[str, dict[int, list[float]]] = {}
    for model_name, benchmark_name, benchmark_avg_score in model_benchmark_scores:
        if benchmark_avg_score is None:
            continue
        benchmark_tier = get_benchmark_tier(str(benchmark_name))
        if benchmark_tier not in {1, 2}:
            continue
        per_model_scores = tier_scores_by_model.setdefault(str(model_name), {1: [], 2: []})
        per_model_scores[benchmark_tier].append(float(benchmark_avg_score))

    models_data = []
    for model, run_count, avg_score, last_run in models_query:
        model_tier_scores = tier_scores_by_model.get(model.codename, {1: [], 2: []})
        models_data.append(
            {
                "model": model,
                "run_count": run_count or 0,
                "avg_score": round(avg_score, 1) if avg_score is not None else None,
                "avg_score_tier_1": _average_or_none(model_tier_scores[1]),
                "avg_score_tier_2": _average_or_none(model_tier_scores[2]),
                "last_run": last_run,
                "max_tier_label": get_tier_label(model.max_benchmark_tier),
            }
        )

    return render_template("models/list.html", models_data=models_data)


@bp.route("/<model_name>")
def view_model(model_name):
    """View detailed information about a specific model."""
    # Get model
    model = g.bench_db.query(Model).filter(Model.codename == model_name).first()
    if not model:
        return "Model not found", 404

    # Get all runs for this model with benchmark info
    runs = (
        g.bench_db.query(Run).filter(Run.model_name == model_name).order_by(Run.run_ts.desc()).all()
    )

    # Calculate best score per benchmark
    best_scores: dict[str, int] = {}
    for run in runs:
        if (
            run.benchmark_name not in best_scores
            or run.normed_score > best_scores[run.benchmark_name]
        ):
            best_scores[run.benchmark_name] = run.normed_score

    return render_template(
        "models/view.html",
        model=model,
        runs=runs,
        best_scores=best_scores,
        max_tier_label=get_tier_label(model.max_benchmark_tier),
    )
