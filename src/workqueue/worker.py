"""Background worker for Barsukas queued tasks."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from threading import Event
from typing import Any

from barsukas.config import Config

import constants
from workqueue.registry import TASK_HANDLERS
from workqueue.task_queue import claim_next_task, mark_task_complete, mark_task_failed
from storage.backend import configure_backend, create_session
from storage.backend.config import BackendType, DataSourceConfig

logger = logging.getLogger(__name__)
STOP_EVENT = Event()
_backend_configured = False


def _handle_shutdown(signum: int, frame: Any) -> None:  # pragma: no cover - signal hook
    logger.info("Shutdown signal received (%s). Finishing current task before exit.", signum)
    STOP_EVENT.set()


def _configure_backend_once() -> None:
    """Configure the backend once at worker startup."""
    global _backend_configured
    if _backend_configured:
        return

    # Check for PostgreSQL mode
    if os.environ.get("STORAGE_BACKEND") == "postgres":
        postgres_url = os.environ.get("POSTGRES_URL")
        if not postgres_url:
            # Build from template + key
            postgres_url = DataSourceConfig.build_postgres_url()

        backend_config = DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=postgres_url,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )
    else:
        # SQLite mode (default)
        backend_config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )

    configure_backend(backend_config)
    _backend_configured = True


def _build_session() -> Any:
    """Build a database session using the globally configured backend."""
    _configure_backend_once()
    return create_session()


def process_task(task: Any, session: Any) -> str:
    handler = TASK_HANDLERS.get(task.task_type)
    if not handler:
        raise ValueError(f"No handler registered for task type {task.task_type}")

    payload = json.loads(task.payload or "{}")
    return handler(session, payload)


def run_worker(poll_interval: float) -> None:
    if os.environ.get("STORAGE_BACKEND") == "postgres":
        logger.info("Starting Barsukas task worker (DB: PostgreSQL)")
    else:
        logger.info("Starting Barsukas task worker (DB: %s)", Config.DB_PATH)
    while True:
        with _build_session() as session:
            task = claim_next_task(session)
            if not task:
                if STOP_EVENT.is_set():
                    logger.info("Shutdown requested; no pending tasks. Exiting worker loop.")
                    break
                time.sleep(poll_interval)
                continue

            try:
                # Commit the RUNNING status so the SQLite write lock is released
                # before handlers run. Handlers may use separate sessions
                # (e.g., via connection_pool) which would deadlock otherwise.
                session.commit()
                logger.info("Processing task %s (%s)", task.id, task.task_type)
                message = process_task(task, session)
                mark_task_complete(session, task, message)
                session.commit()
                logger.info("Task %s completed: %s", task.id, message)
            except Exception as exc:  # pragma: no cover - defensive logging
                session.rollback()
                error_message = str(exc)
                logger.exception("Task %s failed: %s", task.id, error_message)
                mark_task_failed(session, task, error_message)
                session.commit()

        if STOP_EVENT.is_set():
            logger.info("Shutdown requested; finished task %s. Exiting worker loop.", task.id)
            break

        time.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Barsukas background task worker")
    parser.add_argument(
        "--poll-interval", type=float, default=2.0, help="Seconds to wait when queue is empty"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    run_worker(args.poll_interval)


if __name__ == "__main__":
    main()
