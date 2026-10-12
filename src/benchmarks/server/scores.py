"""Precalculate compact run summaries once for all scoreboard pages."""

from threading import RLock
from time import monotonic
from typing import Any

from flask import current_app
from sqlalchemy.orm import Session

from benchmarks.datastore.benchmarks import Question, Run, RunDetail
from benchmarks.datastore.common import Model
from benchmarks.server.analysis import analyze_run_details


class ScoreCache:
    """Shared per-app summaries; TTL also observes writes from other processes."""

    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._expires = 0.0
        self._entries: list[dict[str, Any]] = []
        self._lock = RLock()

    def clear(self, *args: Any) -> None:
        with self._lock:
            self._expires = 0.0
            self._entries = []

    @property
    def expires_at(self) -> float:
        """Deadline for pages rendered from the current summaries."""
        with self._lock:
            return self._expires

    def get(self, db: Session) -> list[dict[str, Any]]:
        with self._lock:
            if monotonic() < self._expires:
                return self._entries
            # Never download question/debug JSON just to calculate scores.
            runs = db.query(Run).all()
            models = {model.codename: model for model in db.query(Model).all()}
            details_by_run: dict[int, list[dict[str, Any]]] = {}
            rows = (
                db.query(
                    RunDetail.run_id,
                    RunDetail.question_id,
                    RunDetail.score,
                    RunDetail.eval_msec,
                    RunDetail.cost_usd,
                    RunDetail.tokens_used,
                    RunDetail.tokens_in,
                    RunDetail.tokens_out,
                    Question.is_excluded.label("is_question_excluded"),
                )
                .outerjoin(Question, RunDetail.question_id == Question.question_id)
                .all()
            )
            for row in rows:
                values = dict(row._mapping)
                run_id = values.pop("run_id")
                details_by_run.setdefault(run_id, []).append(values)
            entries: list[dict[str, Any]] = []
            for run in runs:
                model = models.get(run.model_name)
                if model is None:
                    continue
                metrics = analyze_run_details(
                    run.benchmark_name,
                    details_by_run.get(run.run_id, []),
                    model_path=model.model_path,
                    model_type=model.model_type,
                )
                entries.append({"run": run, "model": model, "metrics": metrics})
            # Cached records must survive the request session closing. They are
            # read-only presentation snapshots, never used for writes.
            for record in [*runs, *models.values()]:
                db.expunge(record)
            self._entries = entries
            self._expires = monotonic() + self.ttl
            return entries


def get_run_summaries(db: Session) -> list[dict[str, Any]]:
    """Return precalculated summaries shared by dashboard and detail pages."""
    cache: ScoreCache = current_app.extensions["benchmark_score_cache"]
    return cache.get(db)
