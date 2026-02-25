#!/usr/bin/python3

"""Model routes - list and view model details."""

from flask import Blueprint, g, render_template
from sqlalchemy import func

from benchmarks.datastore.benchmarks import Run
from benchmarks.datastore.common import Model

bp = Blueprint("models", __name__, url_prefix="/models", template_folder="../templates")


@bp.route("/")
def list_models():
    """List all models with their aggregate statistics."""
    # Get all models with run counts and average scores
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

    models_data = []
    for model, run_count, avg_score, last_run in models_query:
        models_data.append(
            {
                "model": model,
                "run_count": run_count or 0,
                "avg_score": round(avg_score, 1) if avg_score else None,
                "last_run": last_run,
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
    )
