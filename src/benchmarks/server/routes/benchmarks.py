#!/usr/bin/python3

"""Benchmark routes - list and view benchmark details."""

import ipaddress

from flask import Blueprint, g, render_template, request, flash, redirect, url_for, Response
from sqlalchemy import func

from benchmarks.datastore.benchmarks import Benchmark, Question, Run, insert_benchmark
from benchmarks.datastore.common import Model
from benchmarks.lib.utils.factory import get_all_benchmark_codes, get_benchmark_metadata

bp = Blueprint("benchmarks", __name__, url_prefix="/benchmarks")


def _is_authorized_run_request() -> bool:
    """Allow benchmark runs only from direct local-network clients."""
    from flask import current_app

    if current_app.config.get("BENCHMARK_RUNNER_BLOCK_PROXIED_REQUESTS", True):
        for header in ("X-Forwarded-For", "X-Real-IP", "Forwarded", "Via"):
            if request.headers.get(header):
                return False

    remote_addr = request.remote_addr
    if not remote_addr:
        return False

    try:
        remote_ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False

    allowed_networks = current_app.config.get("BENCHMARK_RUNNER_ALLOWED_CIDRS", ())
    return any(remote_ip in network for network in allowed_networks)


def _get_unsynced_benchmark_codes(session) -> list[dict]:
    """Return metadata for benchmarks registered in code but missing from the DB."""
    db_codes = {row.codename for row in session.query(Benchmark.codename).all()}
    unsynced = []
    for code in get_all_benchmark_codes():
        if code not in db_codes:
            metadata = get_benchmark_metadata(code)
            if metadata:
                unsynced.append(
                    {
                        "code": metadata.code,
                        "name": metadata.name,
                        "description": metadata.description,
                    }
                )
    return sorted(unsynced, key=lambda x: x["code"])


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
                "needs_questions": (question_count or 0) == 0,
            }
        )

    unsynced = _get_unsynced_benchmark_codes(g.db)

    return render_template(
        "benchmarks/list.html",
        benchmarks_data=benchmarks_data,
        unsynced_benchmarks=unsynced,
    )


@bp.route("/sync", methods=["POST"])
def sync_benchmarks():
    """Sync all code-registered benchmarks into the database (no question generation)."""
    from flask import current_app

    if not _is_authorized_run_request():
        flash("Benchmark sync is allowed only from local/private direct network clients", "error")
        return redirect(url_for("benchmarks.list_benchmarks"))

    if current_app.config.get("READONLY", False):
        flash("Cannot sync benchmarks: running in read-only mode", "error")
        return redirect(url_for("benchmarks.list_benchmarks"))

    added = 0
    already_present = 0
    for code in get_all_benchmark_codes():
        metadata = get_benchmark_metadata(code)
        if not metadata:
            continue
        success, _msg = insert_benchmark(
            g.db,
            codename=metadata.code,
            displayname=metadata.name,
            description=metadata.description,
        )
        if success:
            added += 1
        else:
            already_present += 1

    flash(
        f"Sync complete: {added} benchmark(s) added, {already_present} already present.",
        "success",
    )
    return redirect(url_for("benchmarks.list_benchmarks"))


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
        if not current_app.config.get("BENCHMARK_RUNNER_ENABLED", True):
            flash("Benchmark execution is disabled on this server", "error")
            return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

        if current_app.config.get("READONLY", False):
            flash("Cannot run benchmark: running in read-only mode", "error")
            return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

        if not _is_authorized_run_request():
            flash(
                "Benchmark execution is allowed only from local/private direct network clients",
                "error",
            )
            return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

        model_name = request.form.get("model_name", "").strip()

        if not model_name:
            flash("Model selection is required", "error")
            return redirect(url_for("benchmarks.run_benchmark", benchmark_name=benchmark_name))

        benchmark = g.db.query(Benchmark).filter(Benchmark.codename == benchmark_name).first()
        if not benchmark:
            flash("Benchmark not found", "error")
            return redirect(url_for("benchmarks.list_benchmarks"))

        model = g.db.query(Model).filter(Model.codename == model_name).first()
        if not model:
            flash("Selected model was not found", "error")
            return redirect(url_for("benchmarks.run_benchmark", benchmark_name=benchmark_name))

        worker = current_app.extensions["benchmark_run_worker"]
        queue_depth = worker.enqueue(benchmark_name=benchmark_name, model_name=model_name)
        flash(
            f"Queued benchmark run for {benchmark_name} on {model_name}. Jobs ahead in queue: {max(queue_depth - 1, 0)}",
            "success",
        )
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    # GET request - show form
    benchmark = g.db.query(Benchmark).filter(Benchmark.codename == benchmark_name).first()
    if not benchmark:
        return "Benchmark not found", 404

    # Get all models
    models = g.db.query(Model).order_by(Model.displayname).all()
    worker_status = current_app.extensions["benchmark_run_worker"].status()

    return render_template(
        "benchmarks/run.html",
        benchmark=benchmark,
        models=models,
        run_enabled=current_app.config.get("BENCHMARK_RUNNER_ENABLED", True),
        run_authorized=_is_authorized_run_request(),
        worker_status=worker_status,
    )


@bp.route("/tasks/<int:task_id>/output")
def task_output(task_id: int):
    """Show stdout/stderr captured for a worker task."""
    from flask import current_app

    worker = current_app.extensions["benchmark_run_worker"]
    output = worker.get_task_output(task_id)
    if output is None:
        return "Task output was not found (it may have expired).", 404

    return Response(output, mimetype="text/plain; charset=utf-8")


@bp.route("/queue")
def queue_status():
    """Display benchmark worker queue and recent run logs."""
    from flask import current_app

    worker_status = current_app.extensions["benchmark_run_worker"].status()
    return render_template(
        "benchmarks/queue.html",
        worker_status=worker_status,
        run_enabled=current_app.config.get("BENCHMARK_RUNNER_ENABLED", True),
        run_authorized=_is_authorized_run_request(),
    )


@bp.route("/tasks/<int:task_id>/cancel", methods=["POST"])
def cancel_task(task_id: int):
    """Cancel a queued benchmark worker task."""
    from flask import current_app

    if not current_app.config.get("BENCHMARK_RUNNER_ENABLED", True):
        flash("Benchmark execution is disabled on this server", "error")
        return redirect(url_for("benchmarks.queue_status"))

    if current_app.config.get("READONLY", False):
        flash("Cannot cancel tasks: running in read-only mode", "error")
        return redirect(url_for("benchmarks.queue_status"))

    if not _is_authorized_run_request():
        flash(
            "Task cancellation is allowed only from local/private direct network clients", "error"
        )
        return redirect(url_for("benchmarks.queue_status"))

    worker = current_app.extensions["benchmark_run_worker"]
    if worker.cancel_task(task_id):
        flash(f"Canceled queued task #{task_id}", "success")
    else:
        flash(f"Task #{task_id} was not queued (it may already be running or finished)", "warning")

    return redirect(url_for("benchmarks.queue_status"))
