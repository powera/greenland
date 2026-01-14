#!/usr/bin/python3

"""Benchmark routes - list and view benchmark details."""

from flask import Blueprint, g, render_template, request, flash, redirect, url_for
from sqlalchemy import func

from benchmarks.datastore.benchmarks import Benchmark, Question, Run
from benchmarks.datastore.common import Model

bp = Blueprint("benchmarks", __name__, url_prefix="/benchmarks")


@bp.route("/")
def list_benchmarks():
    """List all benchmarks with their statistics."""
    # Get all benchmarks with question counts and run statistics
    benchmarks_query = (
        g.db.query(
            Benchmark,
            func.count(Question.question_id).label("question_count"),
            func.count(Run.run_id).label("run_count"),
            func.avg(Run.normed_score).label("avg_score"),
            func.max(Run.run_ts).label("last_run"),
        )
        .outerjoin(Question, Benchmark.codename == Question.benchmark_name)
        .outerjoin(Run, Benchmark.codename == Run.benchmark_name)
        .group_by(Benchmark.codename)
        .order_by(Benchmark.displayname)
        .all()
    )

    benchmarks_data = []
    for benchmark, question_count, run_count, avg_score, last_run in benchmarks_query:
        benchmarks_data.append(
            {
                "benchmark": benchmark,
                "question_count": question_count or 0,
                "run_count": run_count or 0,
                "avg_score": round(avg_score, 1) if avg_score else None,
                "last_run": last_run,
            }
        )

    return render_template("benchmarks/list.html", benchmarks_data=benchmarks_data)


@bp.route("/<benchmark_name>")
def view_benchmark(benchmark_name):
    """View detailed information about a specific benchmark including leaderboard."""
    # Get benchmark
    benchmark = g.db.query(Benchmark).filter(Benchmark.codename == benchmark_name).first()
    if not benchmark:
        return "Benchmark not found", 404

    # Get question count
    question_count = (
        g.db.query(func.count(Question.question_id))
        .filter(Question.benchmark_name == benchmark_name)
        .scalar()
    )

    # Get best run for each model on this benchmark
    subquery = (
        g.db.query(
            Run.model_name,
            func.max(Run.normed_score).label("max_score"),
        )
        .filter(Run.benchmark_name == benchmark_name)
        .group_by(Run.model_name)
        .subquery()
    )

    # Get the actual runs with model info
    leaderboard = (
        g.db.query(Run, Model)
        .join(Model, Run.model_name == Model.codename)
        .join(
            subquery,
            (Run.model_name == subquery.c.model_name) & (Run.normed_score == subquery.c.max_score),
        )
        .filter(Run.benchmark_name == benchmark_name)
        .order_by(Run.normed_score.desc(), Run.run_ts.asc())
        .all()
    )

    return render_template(
        "benchmarks/view.html",
        benchmark=benchmark,
        question_count=question_count,
        leaderboard=leaderboard,
    )


@bp.route("/<benchmark_name>/run", methods=["GET", "POST"])
def run_benchmark(benchmark_name):
    """Run a benchmark on a selected model."""
    from flask import current_app

    if request.method == "POST":
        if current_app.config.get("READONLY", False):
            flash("Cannot run benchmark: running in read-only mode", "error")
            return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

        model_name = request.form.get("model_name", "").strip()

        if not model_name:
            flash("Model selection is required", "error")
            return redirect(url_for("benchmarks.run_benchmark", benchmark_name=benchmark_name))

        # TODO: Implement async job queue for running benchmarks
        # For now, just show a message
        flash(
            f"Benchmark execution not yet implemented. Would run {benchmark_name} on {model_name}",
            "warning",
        )
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    # GET request - show form
    benchmark = g.db.query(Benchmark).filter(Benchmark.codename == benchmark_name).first()
    if not benchmark:
        return "Benchmark not found", 404

    # Get all models
    models = g.db.query(Model).order_by(Model.displayname).all()

    return render_template(
        "benchmarks/run.html",
        benchmark=benchmark,
        models=models,
    )
