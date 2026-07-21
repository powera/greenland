#!/usr/bin/python3

"""Single-threaded benchmark execution worker for server-triggered runs."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BenchmarkRunRequest:
    """Represents a queued benchmark run request."""

    benchmark_name: str
    model_name: str
    task_id: int


@dataclass
class BenchmarkTask:
    """Tracks status and output paths for a queued worker task."""

    task_id: int
    benchmark_name: str
    model_name: str
    state: str
    enqueued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    stdout_path: Optional[Path] = None
    stderr_path: Optional[Path] = None


class BenchmarkRunWorker:
    """Background queue that executes benchmark CLI runs serially."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[BenchmarkRunRequest]" = queue.Queue()
        self._current: Optional[BenchmarkRunRequest] = None
        self._tasks: dict[int, BenchmarkTask] = {}
        self._next_task_id = 1
        self._output_dir = Path(tempfile.gettempdir()) / "benchmark_server_worker"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._output_retention_seconds = 24 * 60 * 60
        self._history_window = timedelta(hours=24)

        # Interactive local-model slot used by Verbalator local-model queries.
        # While occupied, benchmark queue items remain queued but do not start.
        self._interactive_local_model: Optional[str] = None
        self._interactive_local_owner: Optional[str] = None
        self._interactive_local_last_touch: Optional[float] = None
        self._interactive_local_ttl_seconds = 120.0

        self._state_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run_forever, daemon=True, name="benchmark-run-worker"
        )
        self._thread.start()

    def enqueue(self, benchmark_name: str, model_name: str) -> int:
        """Queue a benchmark run and return the resulting queue depth."""
        with self._state_lock:
            task_id = self._next_task_id
            self._next_task_id += 1
            task = BenchmarkTask(
                task_id=task_id,
                benchmark_name=benchmark_name,
                model_name=model_name,
                state="queued",
                enqueued_at=datetime.now(timezone.utc),
                stdout_path=self._output_dir / f"task-{task_id}.stdout.log",
                stderr_path=self._output_dir / f"task-{task_id}.stderr.log",
            )
            self._tasks[task_id] = task
            self._cleanup_expired_outputs_locked()

        request = BenchmarkRunRequest(
            benchmark_name=benchmark_name, model_name=model_name, task_id=task_id
        )
        self._queue.put(request)
        return self._queue.qsize()

    def touch_interactive_local_job(self, model_name: str, owner: str = "verbalator") -> bool:
        """Acquire/refresh the interactive local-model slot.

        Returns False when a benchmark run is currently active or a different interactive
        local model owns the slot and has not expired yet.
        """
        now = time.time()
        with self._state_lock:
            self._expire_interactive_local_job_locked(now)

            # Never let a new interactive job begin while a benchmark is actively running.
            if self._current is not None:
                return False

            if self._interactive_local_model and self._interactive_local_model != model_name:
                return False

            self._interactive_local_model = model_name
            self._interactive_local_owner = owner
            self._interactive_local_last_touch = now
            return True

    def status(self) -> dict[str, Any]:
        """Expose queue + active-run status for templates/routes."""
        with self._state_lock:
            current = self._current
            self._cleanup_expired_outputs_locked()
            self._expire_interactive_local_job_locked(time.time())
            now_utc = datetime.now(timezone.utc)
            queued_tasks = [
                self._serialize_task(task)
                for task in sorted(self._tasks.values(), key=lambda t: t.task_id)
                if task.state == "queued"
            ]
            recent_tasks = [
                self._serialize_task(task)
                for task in sorted(self._tasks.values(), key=lambda t: t.task_id, reverse=True)
                if task.state in {"completed", "failed", "canceled"}
                and task.enqueued_at >= now_utc - self._history_window
            ]
        return {
            "active": (
                None
                if current is None
                else {
                    "task_id": current.task_id,
                    "benchmark_name": current.benchmark_name,
                    "model_name": current.model_name,
                }
            ),
            "queued": len(queued_tasks),
            "queued_tasks": queued_tasks,
            "recent_tasks": recent_tasks,
            "interactive_local_job": self._serialize_interactive_local_job(),
        }

    def cancel_task(self, task_id: int) -> bool:
        """Cancel a queued task. Returns True when cancellation succeeds."""
        with self._state_lock:
            task = self._tasks.get(task_id)
            if not task or task.state != "queued":
                return False

            task.state = "canceled"
            task.finished_at = datetime.now(timezone.utc)
            task.exit_code = None
            return True

    def get_task_output(self, task_id: int) -> Optional[str]:
        """Return captured output for a task if available."""
        with self._state_lock:
            task = self._tasks.get(task_id)
            stdout_path = task.stdout_path if task else None
            stderr_path = task.stderr_path if task else None

        if not stdout_path and not stderr_path:
            return None

        stdout = self._read_output(stdout_path)
        stderr = self._read_output(stderr_path)

        if stdout is None and stderr is None:
            return None

        output_parts: list[str] = []
        if stdout is not None:
            output_parts.append("== STDOUT ==\n" + stdout)
        if stderr is not None:
            output_parts.append("== STDERR ==\n" + stderr)

        return "\n\n".join(output_parts)

    def _run_forever(self) -> None:
        while True:
            request = self._queue.get()

            with self._state_lock:
                task = self._tasks.get(request.task_id)
                if not task or task.state == "canceled":
                    self._queue.task_done()
                    continue

            self._wait_for_interactive_local_job_to_finish()

            with self._state_lock:
                self._current = request
                task = self._tasks.get(request.task_id)
                if task:
                    task.state = "running"
                    task.started_at = datetime.now(timezone.utc)

            try:
                self._run_request(request)
            except Exception:
                logger.exception(
                    "Benchmark worker failed for benchmark=%s model=%s",
                    request.benchmark_name,
                    request.model_name,
                )
            finally:
                with self._state_lock:
                    self._current = None
                self._queue.task_done()

    def _run_request(self, request: BenchmarkRunRequest) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        src_path = repo_root / "src"
        script = src_path / "benchmarks" / "run_benchmark.py"

        env = dict(os.environ)
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{src_path}:{existing_path}" if existing_path else str(src_path)

        cmd = [
            sys.executable,
            str(script),
            "run",
            request.benchmark_name,
            request.model_name,
        ]

        logger.info("Running benchmark via worker: %s", " ".join(cmd))
        task = self._tasks.get(request.task_id)
        stdout_path = (
            task.stdout_path if task else self._output_dir / f"task-{request.task_id}.stdout.log"
        )
        stderr_path = (
            task.stderr_path if task else self._output_dir / f"task-{request.task_id}.stderr.log"
        )

        with (
            stdout_path.open("w", encoding="utf-8") as stdout_file,
            stderr_path.open("w", encoding="utf-8") as stderr_file,
        ):
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                check=False,
            )

        with self._state_lock:
            completed_task = self._tasks.get(request.task_id)
            if completed_task:
                completed_task.finished_at = datetime.now(timezone.utc)
                completed_task.exit_code = result.returncode
                completed_task.state = "completed" if result.returncode == 0 else "failed"

        if result.returncode == 0:
            logger.info(
                "Completed benchmark run benchmark=%s model=%s task_id=%s",
                request.benchmark_name,
                request.model_name,
                request.task_id,
            )
            return

        output_tail = self._read_output_tail(stdout_path)
        error_tail = self._read_output_tail(stderr_path)

        logger.error(
            "Benchmark run failed benchmark=%s model=%s task_id=%s exit=%s stdout=%s stderr=%s",
            request.benchmark_name,
            request.model_name,
            request.task_id,
            result.returncode,
            output_tail,
            error_tail,
        )

    @staticmethod
    def _read_output(path: Optional[Path]) -> Optional[str]:
        if not path or not path.exists():
            return None

        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _serialize_task(task: BenchmarkTask) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "benchmark_name": task.benchmark_name,
            "model_name": task.model_name,
            "state": task.state,
            "enqueued_at": task.enqueued_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "exit_code": task.exit_code,
        }

    def _serialize_interactive_local_job(self) -> Optional[dict[str, Any]]:
        if not self._interactive_local_model or self._interactive_local_last_touch is None:
            return None

        expires_at = self._interactive_local_last_touch + self._interactive_local_ttl_seconds
        return {
            "model_name": self._interactive_local_model,
            "owner": self._interactive_local_owner,
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        }

    @staticmethod
    def _read_output_tail(path: Path, max_chars: int = 2000) -> str:
        if not path.exists():
            return ""

        output = path.read_text(encoding="utf-8", errors="replace")
        return output[-max_chars:]

    def _has_active_interactive_local_job_locked(self, now: float) -> bool:
        self._expire_interactive_local_job_locked(now)
        return self._interactive_local_model is not None

    def _expire_interactive_local_job_locked(self, now: float) -> None:
        if self._interactive_local_last_touch is None:
            return

        if now - self._interactive_local_last_touch <= self._interactive_local_ttl_seconds:
            return

        self._interactive_local_model = None
        self._interactive_local_owner = None
        self._interactive_local_last_touch = None

    def _wait_for_interactive_local_job_to_finish(self) -> None:
        while True:
            with self._state_lock:
                if not self._has_active_interactive_local_job_locked(time.time()):
                    return
            time.sleep(0.2)

    def _cleanup_expired_outputs_locked(self) -> None:
        now = time.time()
        for task_id, task in list(self._tasks.items()):
            if not task.finished_at:
                continue

            if (now - task.finished_at.timestamp()) <= self._output_retention_seconds:
                continue

            if task.stdout_path and task.stdout_path.exists():
                task.stdout_path.unlink(missing_ok=True)

            if task.stderr_path and task.stderr_path.exists():
                task.stderr_path.unlink(missing_ok=True)

            del self._tasks[task_id]
