"""Background worker for Barsukas queued tasks."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from threading import Event

import constants
from config import Config
from wordfreq.storage.backend import create_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig

from barsukas.helpers.task_handlers import TASK_HANDLERS
from barsukas.utils.task_queue import claim_next_task, mark_task_complete, mark_task_failed

logger = logging.getLogger(__name__)
STOP_EVENT = Event()


def _handle_shutdown(signum, frame):  # pragma: no cover - signal hook
    logger.info("Shutdown signal received (%s). Finishing current task before exit.", signum)
    STOP_EVENT.set()


def _build_session():
    backend_config = DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=Config.DB_PATH,
        model=constants.DEFAULT_MODEL,
        debug=Config.DEBUG,
    )
    return create_session(backend_config)


def process_task(task, session):
    handler = TASK_HANDLERS.get(task.task_type)
    if not handler:
        raise ValueError(f"No handler registered for task type {task.task_type}")

    payload = json.loads(task.payload or "{}")
    return handler(session, payload)


def run_worker(poll_interval: float) -> None:
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


def main():
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
