"""Background worker for Barsukas queued tasks."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
from threading import Event
from typing import Any, Optional

from barsukas.config import Config
from barsukas.personas import PersonaConfig

import constants
from workqueue.registry import TASK_HANDLERS
from workqueue.task_queue import claim_next_task, mark_task_complete, mark_task_failed
from storage.backend import configure_backend, create_session, get_data_source_config
from storage.backend.config import BackendType, DataSourceConfig

logger = logging.getLogger(__name__)
STOP_EVENT = Event()
_backend_configured = False


def _handle_shutdown(signum: int, frame: Any) -> None:  # pragma: no cover - signal hook
    logger.info("Shutdown signal received (%s). Finishing current task before exit.", signum)
    STOP_EVENT.set()


def _configure_backend_once(persona: Optional[PersonaConfig] = None) -> None:
    """Configure the worker's backend once at startup.

    The worker operates on the main database only; it never touches the concepts
    database, so the persona's concepts settings are irrelevant here.

    Args:
        persona: The resolved persona. When omitted, the backend is read from
            the environment, preserving the standalone `python -m workqueue.worker`
            entry point.
    """
    global _backend_configured
    if _backend_configured:
        return

    use_word2vec = os.environ.get("USE_WORD2VEC", "false").lower() == "true"

    if persona is not None:
        wants_postgres = persona.use_postgres
        wants_jsonl = persona.use_jsonl
    else:
        backend_env = os.environ.get("STORAGE_BACKEND")
        wants_postgres = backend_env == "postgres"
        wants_jsonl = backend_env == "jsonl"

    backend_config: Optional[DataSourceConfig] = None

    if wants_postgres:
        postgres_url = os.environ.get("POSTGRES_URL")
        if not postgres_url:
            try:
                postgres_url = DataSourceConfig.build_postgres_url()
            except Exception as e:
                # Degrade rather than raise, matching create_app(): a worker that
                # dies on startup takes the whole unified process down with it.
                logger.warning(
                    "PostgreSQL credentials unavailable (%s); worker falling back to SQLite at %s",
                    e,
                    Config.DB_PATH,
                )
                postgres_url = None

        if postgres_url:
            backend_config = DataSourceConfig(
                backend_type=BackendType.POSTGRES,
                postgres_url=postgres_url,
                use_word2vec=use_word2vec,
                model=constants.DEFAULT_MODEL,
                debug=Config.DEBUG,
            )
    elif wants_jsonl:
        # JSONL personas are read-only and disable the worker; if one somehow
        # starts, say so rather than silently operating on the wrong database.
        logger.warning(
            "Worker started under a JSONL backend, which it cannot write to; "
            "using SQLite at %s instead",
            Config.DB_PATH,
        )

    if backend_config is None:
        backend_config = DataSourceConfig(
            backend_type=BackendType.SQLITE,
            sqlite_path=Config.DB_PATH,
            use_word2vec=use_word2vec,
            model=constants.DEFAULT_MODEL,
            debug=Config.DEBUG,
        )

    configure_backend(backend_config)
    _backend_configured = True


def _build_session(persona: Optional[PersonaConfig] = None) -> Any:
    """Build a database session using the globally configured backend."""
    _configure_backend_once(persona)
    return create_session()


def process_task(task: Any, session: Any) -> str:
    handler = TASK_HANDLERS.get(task.task_type)
    if not handler:
        raise ValueError(f"No handler registered for task type {task.task_type}")

    payload = json.loads(task.payload or "{}")
    return handler(session, payload)


def run_worker(poll_interval: float, persona: Optional[PersonaConfig] = None) -> None:
    """Poll for queued tasks and run them until shutdown is requested.

    Args:
        poll_interval: Seconds to sleep when the queue is empty
        persona: The resolved persona, used to pick the main database backend.
    """
    _configure_backend_once(persona)
    logger.info(
        "Starting Barsukas task worker (DB: %s)",
        get_data_source_config().backend_type.value,
    )
    while True:
        with _build_session(persona) as session:
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
    parser.add_argument(
        "--use-word2vec",
        "--use_word2vec",
        dest="use_word2vec",
        action="store_true",
        help="Enable pgvector embedding read/write operations (opt-in)",
    )
    args = parser.parse_args()
    if args.use_word2vec:
        os.environ["USE_WORD2VEC"] = "true"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
    )
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    run_worker(args.poll_interval)


if __name__ == "__main__":
    main()
