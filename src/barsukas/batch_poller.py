"""Periodic background poller for Barsukas-submitted OpenAI Batch jobs.

Runs inside the unified Barsukas server (alongside the workqueue worker
thread). Every 5 minutes it:

1. Scans the batch-tracking DB for ``BatchQueue`` rows submitted by the
   ``barsukas_decompose`` agent that are still in flight
   (``submitted`` / ``processing``).
2. For each unique ``batch_id``, calls ``BatchQueueManager.check_batch_status``
   so the local state mirrors OpenAI.
3. If a batch has reached ``completed`` on OpenAI, downloads results via
   ``retrieve_batch_results`` and applies them to the main database with
   ``apply_sentence_translation_results``.

If no batches are in flight the poller does nothing and goes back to sleep.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from sqlalchemy.orm import Session

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    BatchRequestStatus,
    create_batch_database_session,
)
from clients.openai.batch_client import BatchStatus, OpenAIBatchClient
from sentences.batch_completion import apply_sentence_translation_results

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 300
_AGENT_NAME = "barsukas_decompose"
_IN_FLIGHT_STATUSES = (
    BatchRequestStatus.SUBMITTED.value,
    BatchRequestStatus.PROCESSING.value,
)


def _collect_active_batch_ids(batch_session: Session) -> list[str]:
    rows = (
        batch_session.query(BatchQueue.batch_id)
        .filter(BatchQueue.agent_name == _AGENT_NAME)
        .filter(BatchQueue.batch_id.isnot(None))
        .filter(BatchQueue.status.in_(_IN_FLIGHT_STATUSES))
        .distinct()
        .all()
    )
    return [row[0] for row in rows if row[0]]


def poll_once(main_session_factory: Callable[[], Session]) -> None:
    """One iteration of the poller. Safe to call from any thread."""
    batch_session = create_batch_database_session()
    try:
        manager = BatchQueueManager(batch_session, OpenAIBatchClient())
        batch_ids = _collect_active_batch_ids(batch_session)
        if not batch_ids:
            logger.debug("No in-flight barsukas_decompose batches")
            return

        logger.info("Checking %s in-flight batch(es): %s", len(batch_ids), batch_ids)
        for batch_id in batch_ids:
            try:
                info = manager.check_batch_status(batch_id)
            except Exception:
                logger.exception("Failed to check status for batch %s", batch_id)
                continue

            status = info.get("status")
            logger.info("Batch %s status: %s", batch_id, status)

            if status != BatchStatus.COMPLETED.value:
                continue

            try:
                manager.retrieve_batch_results(batch_id)
            except Exception:
                logger.exception("Failed to retrieve results for batch %s", batch_id)
                continue

            completed = manager.get_completed_requests(agent_name=_AGENT_NAME, batch_id=batch_id)
            if not completed:
                logger.warning("Batch %s reported completed but no requests found", batch_id)
                continue

            main_session = main_session_factory()
            try:
                result = apply_sentence_translation_results(completed, main_session, batch_id)
                main_session.commit()
                logger.info(
                    "Applied batch %s: %s sentences updated, %s failed",
                    batch_id,
                    result["updated"],
                    result["failed"],
                )
            except Exception:
                main_session.rollback()
                logger.exception("Failed to apply results for batch %s", batch_id)
            finally:
                main_session.close()
    finally:
        batch_session.close()


def run_poller(
    main_session_factory: Callable[[], Session],
    stop_event: threading.Event,
    interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """Loop forever calling :func:`poll_once` every ``interval_seconds``."""
    logger.info("Starting batch poller (interval=%ss)", interval_seconds)
    # Initial small delay so the server has time to finish booting.
    if stop_event.wait(timeout=min(30.0, interval_seconds)):
        return
    while not stop_event.is_set():
        try:
            poll_once(main_session_factory)
        except Exception:
            logger.exception("Batch poller iteration failed")
        if stop_event.wait(timeout=interval_seconds):
            break
    logger.info("Batch poller stopped")


def start_poller_thread(
    main_session_factory: Callable[[], Session],
    stop_event: threading.Event,
    interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> threading.Thread:
    """Spawn the poller as a daemon thread and return it."""
    thread = threading.Thread(
        target=run_poller,
        args=(main_session_factory, stop_event, interval_seconds),
        name="BarsukasBatchPoller",
        daemon=True,
    )
    thread.start()
    return thread
