#!/usr/bin/python3

"""Run routes - view run details and comparisons."""

import json
import re

from flask import Blueprint, g, render_template, request

from benchmarks.datastore.benchmarks import (
    get_recent_runs,
    get_run_by_run_id,
    Question,
    Run,
    RunDetail,
)
from benchmarks.datastore.common import Model
from benchmarks.server.analysis import analyze_run_details, correctness_threshold

bp = Blueprint("runs", __name__, url_prefix="/runs", template_folder="../templates")


@bp.route("/")
def list_runs():
    """List recent benchmark runs."""
    runs = get_recent_runs(g.bench_db)
    return render_template("runs/list.html", runs=runs)


def _question_sort_key(detail: dict) -> tuple[int, str]:
    """Sort benchmark question IDs by numeric suffix when available."""
    question_id = detail.get("question_id") or ""
    match = re.search(r":(\d+)$", question_id)
    if match:
        return int(match.group(1)), question_id
    return 10**9, question_id


def _format_json_for_display(value: object) -> str:
    """Format JSON-like values for template display without ASCII escaping."""
    return json.dumps(value, indent=2, ensure_ascii=False)


def _is_python_coding_benchmark(question_id: str) -> bool:
    return bool(re.match(r"^03\d{2}_python_", question_id))


def _is_python_coding_run(benchmark_name: str) -> bool:
    return bool(re.match(r"^03\d{2}_python_", benchmark_name))


@bp.route("/<int:run_id>")
def view_run(run_id):
    """View detailed results for a specific run."""
    # Get run details using existing function
    run_data = get_run_by_run_id(run_id, g.bench_db)

    if not run_data:
        return "Run not found", 404

    # Get model and benchmark info from database
    run = g.bench_db.query(Run).filter(Run.run_id == run_id).first()
    model = g.bench_db.query(Model).filter(Model.codename == run.model_name).first()

    ordered_questions = sorted(run_data["details"], key=_question_sort_key)
    is_python_coding_run = _is_python_coding_run(run_data["benchmark_name"])
    metrics = analyze_run_details(
        run_data["benchmark_name"],
        ordered_questions,
        model_path=model.model_path if model else None,
        model_type=model.model_type if model else None,
    )
    total_questions = len(run_data["details"])
    threshold = correctness_threshold(run_data["benchmark_name"])

    for detail in ordered_questions:
        question_info_json = detail.get("question_info_json") or {}
        debug_json = detail.get("debug_json") or {}

        expected_answer = question_info_json.get("correct_answer")
        if expected_answer is None:
            expected_answer = debug_json.get("expected", debug_json.get("expected_answer"))

        model_response = debug_json.get("response")
        if model_response is None:
            model_response = debug_json.get("model_answer", debug_json.get("model_response"))

        question_id = detail.get("question_id") or ""
        if _is_python_coding_benchmark(question_id):
            expected_answer = question_info_json.get("correct_answer", {})
            detail["response_label"] = "Submitted code"
            detail["test_case_results"] = debug_json.get("test_case_results")
        else:
            detail["expected_label"] = "Expected"
            detail["expected_display"] = (
                _format_json_for_display(expected_answer)
                if isinstance(expected_answer, (dict, list, tuple))
                else expected_answer
            )
            detail["response_label"] = "Provided"

        detail["response_display"] = (
            _format_json_for_display(model_response)
            if isinstance(model_response, (dict, list, tuple))
            else model_response
        )

    return render_template(
        "runs/view.html",
        run_data=run_data,
        model=model,
        run=run,
        total_questions=total_questions,
        correct_count=metrics.correct_count,
        incorrect_count=metrics.incorrect_count,
        avg_time=metrics.avg_time_msec,
        median_time=metrics.median_time_msec,
        total_cost=metrics.total_cost_usd,
        total_tokens=metrics.total_tokens,
        ordered_questions=ordered_questions,
        correctness_threshold=threshold,
        is_python_coding_run=is_python_coding_run,
        included_question_count=metrics.included_question_count,
        excluded_question_count=metrics.excluded_question_count,
        effective_score=metrics.effective_score,
        outlier_count=metrics.outlier_count,
        price_diagnostics=metrics.price_diagnostics,
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
        run_data = get_run_by_run_id(run_id, g.bench_db)
        if run_data:
            # Get model info
            run = g.bench_db.query(Run).filter(Run.run_id == run_id).first()
            model = g.bench_db.query(Model).filter(Model.codename == run.model_name).first()

            # Calculate stats
            total_questions = len(run_data["details"])
            threshold = correctness_threshold(run_data["benchmark_name"])
            metrics = analyze_run_details(
                run_data["benchmark_name"],
                run_data["details"],
                model_path=model.model_path if model else None,
                model_type=model.model_type if model else None,
            )

            runs_data.append(
                {
                    "run_id": run_id,
                    "run_data": run_data,
                    "model": model,
                    "run": run,
                    "correct_count": metrics.correct_count,
                    "total_questions": total_questions,
                    "avg_time": metrics.avg_time_msec,
                    "total_cost": metrics.total_cost_usd,
                    "total_tokens": metrics.total_tokens,
                    "effective_score": metrics.effective_score,
                    "included_question_count": metrics.included_question_count,
                    "excluded_question_count": metrics.excluded_question_count,
                    "median_time": metrics.median_time_msec,
                    "price_diagnostics": metrics.price_diagnostics,
                    "threshold": threshold,
                }
            )

    return render_template("runs/compare.html", runs=runs_data)
