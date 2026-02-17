#!/usr/bin/python3

"""Single-threaded benchmark execution worker for server-triggered runs."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BenchmarkRunRequest:
    """Represents a queued benchmark run request."""

    benchmark_name: str
    model_name: str


class BenchmarkRunWorker:
    """Background queue that executes benchmark CLI runs serially."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[BenchmarkRunRequest]" = queue.Queue()
        self._current: Optional[BenchmarkRunRequest] = None
        self._state_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="benchmark-run-worker")
        self._thread.start()

    def enqueue(self, benchmark_name: str, model_name: str) -> int:
        """Queue a benchmark run and return the resulting queue depth."""
        request = BenchmarkRunRequest(benchmark_name=benchmark_name, model_name=model_name)
        self._queue.put(request)
        return self._queue.qsize()

    def status(self) -> dict:
        """Expose queue + active-run status for templates/routes."""
        with self._state_lock:
            current = self._current
        return {
            "active": None
            if current is None
            else {
                "benchmark_name": current.benchmark_name,
                "model_name": current.model_name,
            },
            "queued": self._queue.qsize(),
        }

    def _run_forever(self) -> None:
        while True:
            request = self._queue.get()
            with self._state_lock:
                self._current = request

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
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            logger.info(
                "Completed benchmark run benchmark=%s model=%s",
                request.benchmark_name,
                request.model_name,
            )
            return

        logger.error(
            "Benchmark run failed benchmark=%s model=%s exit=%s stdout=%s stderr=%s",
            request.benchmark_name,
            request.model_name,
            result.returncode,
            result.stdout[-2000:],
            result.stderr[-2000:],
        )
