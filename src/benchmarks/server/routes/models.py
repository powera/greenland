#!/usr/bin/python3

"""Model routes - list and view model details."""

from typing import Any

from flask import Blueprint, g, render_template
from sqlalchemy import func

from benchmarks.datastore.benchmarks import Run
from benchmarks.datastore.common import Model
from benchmarks.server.analysis import (
    describe_run_warnings,
    get_score_color,
)
from benchmarks.server.scores import get_run_summaries
from benchmarks.tiers import get_benchmark_tier, get_model_capability_label

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
                "max_capability_label": get_model_capability_label(model.max_benchmark_tier),
            }
        )

    return render_template("models/list.html", models_data=models_data)


@bp.route("/<model_name>")
def view_model(model_name: str) -> Any:
    """View detailed information about a specific model."""
    model = g.bench_db.query(Model).filter(Model.codename == model_name).first()
    if not model:
        return "Model not found", 404

    run_entries: list[dict[str, Any]] = []
    for summary in get_run_summaries(g.bench_db):
        run = summary["run"]
        if run.model_name != model_name:
            continue
        metrics = summary["metrics"]
        run_entries.append(
            {
                "run": run,
                "metrics": metrics,
                "avg_cost_micro_usd": (
                    metrics.total_cost_usd / metrics.included_question_count * 1_000_000
                    if metrics.included_question_count
                    else 0.0
                ),
                "score_color": get_score_color(metrics.effective_score),
                "warnings": describe_run_warnings(metrics),
            }
        )

    run_entries.sort(key=lambda entry: entry["run"].run_ts, reverse=True)

    best_scores: dict[str, int] = {}
    for entry in run_entries:
        benchmark_name = entry["run"].benchmark_name
        effective_score = entry["metrics"].effective_score
        if benchmark_name not in best_scores or effective_score > best_scores[benchmark_name]:
            best_scores[benchmark_name] = effective_score

    return render_template(
        "models/view.html",
        model=model,
        run_entries=run_entries,
        best_scores=best_scores,
        max_capability_label=get_model_capability_label(model.max_benchmark_tier),
    )
