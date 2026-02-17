#!/usr/bin/python3

"""Run routes - view run details and comparisons."""

import json

from flask import Blueprint, g, render_template, request

from benchmarks.datastore.benchmarks import get_run_by_run_id, Question, Run, RunDetail
from benchmarks.datastore.common import Model

bp = Blueprint("runs", __name__, url_prefix="/runs")


def _correctness_threshold(benchmark_name: str) -> int:
    return 70 if benchmark_name == "0062_sentence_decomposition" else 100


@bp.route("/<int:run_id>")
def view_run(run_id):
    """View detailed results for a specific run."""
    # Get run details using existing function
    run_data = get_run_by_run_id(run_id, g.db)

    if not run_data:
        return "Run not found", 404

    # Get model and benchmark info from database
    run = g.db.query(Run).filter(Run.run_id == run_id).first()
    model = g.db.query(Model).filter(Model.codename == run.model_name).first()

    # Calculate statistics
    total_questions = len(run_data["details"])
    threshold = _correctness_threshold(run_data["benchmark_name"])
    correct_count = sum(1 for d in run_data["details"] if (d.get("score") or 0) >= threshold)
    incorrect_count = total_questions - correct_count

    total_time = sum(d["eval_msec"] or 0 for d in run_data["details"])
    avg_time = total_time / total_questions if total_questions > 0 else 0


    # Group questions by correctness for easier viewing
    correct_questions = [d for d in run_data["details"] if (d.get("score") or 0) >= threshold]
    incorrect_questions = [d for d in run_data["details"] if (d.get("score") or 0) < threshold]

    return render_template(
        "runs/view.html",
        run_data=run_data,
        model=model,
        run=run,
        total_questions=total_questions,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        avg_time=avg_time,
        correct_questions=correct_questions,
        incorrect_questions=incorrect_questions,
        correctness_threshold=threshold,
    )


@bp.route("/compare")
def compare_runs():
    """Compare multiple runs side by side."""
    # Get run IDs from query params
    run_ids = request.args.getlist("run_id", type=int)

    if not run_ids:
        return render_template("runs/compare.html", runs=[])

    if len(run_ids) > 5:
        return "Maximum 5 runs can be compared at once", 400

    # Get data for each run
    runs_data = []
    for run_id in run_ids:
        run_data = get_run_by_run_id(run_id, g.db)
        if run_data:
            # Get model info
            run = g.db.query(Run).filter(Run.run_id == run_id).first()
            model = g.db.query(Model).filter(Model.codename == run.model_name).first()

            # Calculate stats
            total_questions = len(run_data["details"])
            threshold = _correctness_threshold(run_data["benchmark_name"])
            correct_count = sum(1 for d in run_data["details"] if (d.get("score") or 0) >= threshold)
            avg_time = (
                sum(d["eval_msec"] or 0 for d in run_data["details"]) / total_questions
                if total_questions > 0
                else 0
            )

            runs_data.append(
                {
                    "run_id": run_id,
                    "run_data": run_data,
                    "model": model,
                    "run": run,
                    "correct_count": correct_count,
                    "total_questions": total_questions,
                    "avg_time": avg_time,
                }
            )

    return render_template("runs/compare.html", runs=runs_data)
