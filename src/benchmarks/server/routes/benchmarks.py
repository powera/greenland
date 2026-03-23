#!/usr/bin/python3

"""Benchmark routes - list and view benchmark details."""

import json
import ipaddress

from flask import Blueprint, g, render_template, request, flash, redirect, url_for, Response
from sqlalchemy import func

from benchmarks.datastore.benchmarks import (
    Benchmark,
    Question,
    Run,
    RunDetail,
    insert_benchmark,
    set_question_exclusion,
)
from benchmarks.datastore.common import Model, decode_json
from benchmarks.server.analysis import analyze_run_details
from benchmarks.lib.utils.factory import get_all_benchmark_codes, get_benchmark_metadata
from benchmarks.tiers import (
    BENCHMARK_TIERS,
    get_benchmark_tier,
    get_model_capability_label,
    get_model_capability_level,
    get_tier_label,
    model_can_run_benchmark,
)

bp = Blueprint("benchmarks", __name__, url_prefix="/benchmarks", template_folder="../templates")


def _extract_prompt_details(question_info: dict) -> dict:
    """Extract prompt-related fields from a question payload."""
    return {
        key: value
        for key, value in question_info.items()
        if isinstance(key, str) and "prompt" in key.lower()
    }


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
                        "category": metadata.category,
                    }
                )
    return sorted(unsynced, key=lambda x: x["code"])


@bp.route("/")
def list_benchmarks():
    """List all benchmarks with their statistics."""
    # Get all benchmarks with question counts and run statistics
    benchmarks_query = (
        g.bench_db.query(
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

    unsynced = _get_unsynced_benchmark_codes(g.bench_db)

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
    updated = 0
    for code in get_all_benchmark_codes():
        metadata = get_benchmark_metadata(code)
        if not metadata:
            continue
        success, _msg = insert_benchmark(
            g.bench_db,
            codename=metadata.code,
            displayname=metadata.name,
            description=metadata.description,
            category=metadata.category,
        )
        if success:
            added += 1
        else:
            already_present += 1
            # Update the category for existing benchmarks
            existing = g.bench_db.query(Benchmark).filter(Benchmark.codename == code).first()
            if existing and existing.category != metadata.category:
                existing.category = metadata.category
                updated += 1

    g.bench_db.commit()
    flash(
        f"Sync complete: {added} benchmark(s) added, {already_present} already present"
        + (f", {updated} category update(s)." if updated else "."),
        "success",
    )
    return redirect(url_for("benchmarks.list_benchmarks"))


@bp.route("/<benchmark_name>")
def view_benchmark(benchmark_name):
    """View detailed information about a specific benchmark including leaderboard."""
    # Get benchmark
    benchmark = g.bench_db.query(Benchmark).filter(Benchmark.codename == benchmark_name).first()
    if not benchmark:
        return "Benchmark not found", 404

    # Get question count
    question_count = (
        g.bench_db.query(func.count(Question.question_id))
        .filter(Question.benchmark_name == benchmark_name)
        .scalar()
    )

    raw_questions = (
        g.bench_db.query(Question)
        .filter(Question.benchmark_name == benchmark_name)
        .order_by(Question.question_id)
        .limit(100)
        .all()
    )

    question_previews = []
    for question in raw_questions:
        question_info = decode_json(question.question_info_json)
        prompt_details = _extract_prompt_details(question_info)
        question_previews.append(
            {
                "question_id": question.question_id,
                "question_text": question_info.get("question_text")
                or question_info.get("question"),
                "prompt_details": prompt_details,
                "question_info_pretty": json.dumps(
                    question_info,
                    ensure_ascii=False,
                    indent=2,
                ),
                "is_excluded": question.is_excluded,
                "exclusion_reason": question.exclusion_reason,
            }
        )

    leaderboard_rows = (
        g.bench_db.query(Run, Model, RunDetail, Question)
        .join(Model, Run.model_name == Model.codename)
        .outerjoin(RunDetail, RunDetail.run_id == Run.run_id)
        .outerjoin(Question, RunDetail.question_id == Question.question_id)
        .filter(Run.benchmark_name == benchmark_name)
        .order_by(Run.model_name, Run.run_id)
        .all()
    )
    best_runs_by_model: dict[str, dict] = {}
    current_model_name = None
    current_run_id = None
    current_run = None
    current_model = None
    current_details: list[dict] = []
    for run, model, detail, question in leaderboard_rows + [(None, None, None, None)]:
        row_model_name = run.model_name if run is not None else None
        row_run_id = run.run_id if run is not None else None
        if current_run is not None and (
            row_model_name != current_model_name or row_run_id != current_run_id
        ):
            metrics = analyze_run_details(
                current_run.benchmark_name,
                current_details,
                model_path=current_model.model_path if current_model else None,
                model_type=current_model.model_type if current_model else None,
            )
            candidate = {
                "run": current_run,
                "model": current_model,
                "metrics": metrics,
            }
            if current_model_name is None:
                current_details = []
                continue
            existing = best_runs_by_model.get(current_model_name)
            if existing is None or (
                candidate["metrics"].effective_score,
                candidate["run"].run_ts,
                candidate["run"].run_id,
            ) > (
                existing["metrics"].effective_score,
                existing["run"].run_ts,
                existing["run"].run_id,
            ):
                best_runs_by_model[current_model_name] = candidate

            current_details = []

        current_model_name = row_model_name
        current_run_id = row_run_id
        current_run = run
        current_model = model
        if detail is not None:
            current_details.append(
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

    leaderboard = sorted(
        best_runs_by_model.values(),
        key=lambda entry: (
            entry["metrics"].effective_score,
            entry["run"].run_ts,
            entry["run"].run_id,
        ),
        reverse=True,
    )
    excluded_question_count = sum(1 for question in question_previews if question["is_excluded"])

    return render_template(
        "benchmarks/view.html",
        benchmark=benchmark,
        question_count=question_count,
        question_previews=question_previews,
        leaderboard=leaderboard,
        excluded_question_count=excluded_question_count,
    )


@bp.route("/questions/<question_id>/exclude", methods=["POST"])
def exclude_question(question_id: str):
    """Exclude a benchmark question from aggregate results."""
    from flask import current_app

    benchmark_name = request.form.get("benchmark_name", "").strip()
    if current_app.config.get("READONLY", False):
        flash("Cannot update question exclusions: running in read-only mode", "error")
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    if not _is_authorized_run_request():
        flash(
            "Question exclusion changes are allowed only from local/private direct clients", "error"
        )
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Please provide a reason when excluding a question.", "error")
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    success, message = set_question_exclusion(
        g.bench_db,
        question_id,
        is_excluded=True,
        exclusion_reason=reason,
    )
    flash(message, "success" if success else "error")
    return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))


@bp.route("/questions/<question_id>/include", methods=["POST"])
def include_question(question_id: str):
    """Re-include a benchmark question in aggregate results."""
    from flask import current_app

    benchmark_name = request.form.get("benchmark_name", "").strip()
    if current_app.config.get("READONLY", False):
        flash("Cannot update question exclusions: running in read-only mode", "error")
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    if not _is_authorized_run_request():
        flash(
            "Question exclusion changes are allowed only from local/private direct clients", "error"
        )
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    success, message = set_question_exclusion(
        g.bench_db,
        question_id,
        is_excluded=False,
    )
    flash(message, "success" if success else "error")
    return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))


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

        benchmark = g.bench_db.query(Benchmark).filter(Benchmark.codename == benchmark_name).first()
        if not benchmark:
            flash("Benchmark not found", "error")
            return redirect(url_for("benchmarks.list_benchmarks"))

        model = g.bench_db.query(Model).filter(Model.codename == model_name).first()
        if not model:
            flash("Selected model was not found", "error")
            return redirect(url_for("benchmarks.run_benchmark", benchmark_name=benchmark_name))

        if not model_can_run_benchmark(model, benchmark_name):
            benchmark_tier = get_benchmark_tier(benchmark_name)
            flash(
                f"{model.displayname} is limited to {get_model_capability_label(get_model_capability_level(model))} and "
                f"cannot run {get_tier_label(benchmark_tier)} tasks.",
                "error",
            )
            return redirect(url_for("benchmarks.run_benchmark", benchmark_name=benchmark_name))

        worker = current_app.extensions["benchmark_run_worker"]
        queue_depth = worker.enqueue(benchmark_name=benchmark_name, model_name=model_name)
        flash(
            f"Queued benchmark run for {benchmark_name} on {model_name}. Jobs ahead in queue: {max(queue_depth - 1, 0)}",
            "success",
        )
        return redirect(url_for("benchmarks.view_benchmark", benchmark_name=benchmark_name))

    # GET request - show form
    benchmark = g.bench_db.query(Benchmark).filter(Benchmark.codename == benchmark_name).first()
    if not benchmark:
        return "Benchmark not found", 404

    # Get all models
    models = g.bench_db.query(Model).order_by(Model.displayname).all()
    benchmark_tier = get_benchmark_tier(benchmark_name)
    model_options = [
        {
            "model": model,
            "supported": model_can_run_benchmark(model, benchmark_name),
            "model_capability_level": get_model_capability_level(model),
            "model_capability_label": get_model_capability_label(get_model_capability_level(model)),
        }
        for model in models
    ]
    worker_status = current_app.extensions["benchmark_run_worker"].status()

    return render_template(
        "benchmarks/run.html",
        benchmark=benchmark,
        model_options=model_options,
        benchmark_tier=benchmark_tier,
        benchmark_tier_label=get_tier_label(benchmark_tier),
        tier_definitions=BENCHMARK_TIERS,
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
