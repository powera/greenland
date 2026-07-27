#!/usr/bin/python3

"""Model routes - list and view model details."""

from itertools import groupby
from typing import Any

from flask import Blueprint, g, render_template
from sqlalchemy import func

from benchmarks.datastore.benchmarks import Question, Run, RunDetail
from benchmarks.datastore.common import Model
from benchmarks.server.analysis import (
    analyze_run_details,
    describe_run_warnings,
    get_score_color,
)
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

    # Scores here are recomputed from RunDetail with analyze_run_details rather
    # than read from Run.normed_score, so this page agrees with the dashboard.
    run_rows = (
        g.bench_db.query(Run, RunDetail, Question)
        .outerjoin(RunDetail, RunDetail.run_id == Run.run_id)
        .outerjoin(Question, RunDetail.question_id == Question.question_id)
        .filter(Run.model_name == model_name)
        .order_by(Run.run_id)
        .all()
    )

    run_entries: list[dict[str, Any]] = []
    for _run_id, grouped_rows in groupby(run_rows, key=lambda row: row[0].run_id):
        run = None
        detail_records: list[dict[str, Any]] = []
        for current_run, detail, question in grouped_rows:
            run = current_run
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
            model_path=model.model_path,
            model_type=model.model_type,
        )
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
