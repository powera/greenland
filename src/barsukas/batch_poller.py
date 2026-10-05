"""Periodic background poller for Barsukas-submitted OpenAI Batch jobs.

Runs inside the unified Barsukas server (alongside the workqueue worker
thread). Every 5 minutes it:

1. Scans the batch-tracking DB for ``BatchQueue`` rows submitted by the
   sentence translate/decompose agents, the ``voras`` lemma-populate
   agent (``words.translation_batch``), or a staged job registered in
   ``workqueue.registry.LLM_JOBS`` (``lape``) that are still in flight
   (``submitted`` / ``processing``).
2. For each unique ``batch_id``, calls ``BatchQueueManager.check_batch_status``
   so the local state mirrors OpenAI.
3. If a batch has reached ``completed`` on OpenAI, downloads results via
   ``retrieve_batch_results`` and applies them to the main database with
   the agent's applier (``apply_results_for_agent`` for sentences,
   ``apply_populate_results`` for lemma translations,
   ``workqueue.llm_batch.complete_rows`` for staged jobs, which also
   submits a job's next stage once the whole run is through this one).
   A staged job's batch that failed or expired is marked finished so the
   rest of its run can move on.

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
from sentences.batch_completion import (
    DECOMPOSE_AGENT_NAME,
    TRANSLATE_AGENT_NAME,
    apply_results_for_agent,
    apply_sentence_translation_results,
)
from words.translation_batch import AGENT_NAME as LEMMA_TRANSLATE_AGENT_NAME
from words.translation_batch import apply_populate_results

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 300
# zvirblis's one-shot combined batches, from before it ran as a staged job.
LEGACY_ZVIRBLIS_AGENT_NAME = "zvirblis"
_LEGACY_AGENT_NAMES = (DECOMPOSE_AGENT_NAME, TRANSLATE_AGENT_NAME, LEMMA_TRANSLATE_AGENT_NAME)
_TERMINAL_FAILED_STATUSES = (
    BatchStatus.FAILED.value,
    BatchStatus.EXPIRED.value,
    BatchStatus.CANCELLED.value,
)


def _agent_names() -> tuple[str, ...]:
    """Legacy batch agents plus every staged job in workqueue.registry.LLM_JOBS."""
    from workqueue.registry import LLM_JOBS

    return _LEGACY_AGENT_NAMES + tuple(LLM_JOBS)


_IN_FLIGHT_STATUSES = (
    BatchRequestStatus.SUBMITTED.value,
    BatchRequestStatus.PROCESSING.value,
)


def _collect_active_batch_ids(batch_session: Session) -> list[tuple[str, str]]:
    """Return ``(batch_id, agent_name)`` for every in-flight Barsukas batch."""
    rows = (
        batch_session.query(BatchQueue.batch_id, BatchQueue.agent_name)
        .filter(BatchQueue.agent_name.in_(_agent_names()))
        .filter(BatchQueue.batch_id.isnot(None))
        .filter(BatchQueue.status.in_(_IN_FLIGHT_STATUSES))
        .distinct()
        .all()
    )
    return [(row[0], row[1]) for row in rows if row[0]]


def apply_completed_requests(
    agent_name: str, requests: list[BatchQueue], main_session: Session, batch_id: str
) -> dict[str, int]:
    """Apply one agent's completed requests with that agent's applier.

    The single dispatch point for Barsukas-applied batches: the poller and the
    batch page's "check and finish" both come through here, so an agent the
    poller knows is one the page knows too.

    Staged jobs (``workqueue.registry.LLM_JOBS``) are applied by
    ``workqueue.llm_batch.complete_rows``, which also submits the job's next
    stage once every item of the run has finished this one.

    Raises:
        ValueError: For an agent with no applier here.
    """
    from workqueue.llm_batch import complete_rows, is_staged_row
    from workqueue.registry import get_llm_job

    job = get_llm_job(agent_name)
    staged = [row for row in requests if job is not None and is_staged_row(row)]
    legacy = [row for row in requests if not (job is not None and is_staged_row(row))]
    totals: dict[str, int] = {"updated": 0, "failed": 0}
    results = []
    if job is not None and staged:
        results.append(complete_rows(job, staged, main_session, batch_id))
    if legacy:
        results.append(_apply_legacy_requests(agent_name, legacy, main_session, batch_id))
    for result in results:
        for key, value in result.items():
            totals[key] = totals.get(key, 0) + value
    return totals


def _apply_legacy_requests(
    agent_name: str, requests: list[BatchQueue], main_session: Session, batch_id: str
) -> dict[str, int]:
    """Rows submitted before an agent moved to a staged job (or never moved)."""
    if agent_name == LEMMA_TRANSLATE_AGENT_NAME:
        return apply_populate_results(requests, main_session, batch_id)
    if agent_name == LEGACY_ZVIRBLIS_AGENT_NAME:
        return apply_sentence_translation_results(requests, main_session, batch_id)
    return apply_results_for_agent(agent_name, requests, main_session, batch_id)


def _fail_staged_job_batch(
    agent_name: str,
    batch_id: str,
    manager: BatchQueueManager,
    main_session_factory: Callable[[], Session],
) -> None:
    """Let a staged job's run move on past a batch that will never complete."""
    from workqueue.llm_batch import fail_batch
    from workqueue.registry import get_llm_job

    job = get_llm_job(agent_name)
    if job is None:
        return
    main_session = main_session_factory()
    try:
        submitted = fail_batch(job, batch_id, manager, main_session)
        logger.warning(
            "Batch %s (%s) did not complete; %s next-stage call(s) submitted",
            batch_id,
            agent_name,
            submitted,
        )
    except Exception:
        main_session.rollback()
        logger.exception("Failed to handle failed batch %s", batch_id)
    finally:
        main_session.close()


def poll_once(main_session_factory: Callable[[], Session]) -> None:
    """One iteration of the poller. Safe to call from any thread."""
    batch_session = create_batch_database_session()
    try:
        manager = BatchQueueManager(batch_session, OpenAIBatchClient())
        active = _collect_active_batch_ids(batch_session)
        if not active:
            logger.debug("No in-flight Barsukas batches")
            return

        logger.info("Checking %s in-flight batch(es): %s", len(active), active)
        for batch_id, agent_name in active:
            try:
                info = manager.check_batch_status(batch_id)
            except Exception:
                logger.exception("Failed to check status for batch %s", batch_id)
                continue

            status = info.get("status")
            logger.info("Batch %s (%s) status: %s", batch_id, agent_name, status)

            if status in _TERMINAL_FAILED_STATUSES:
                _fail_staged_job_batch(agent_name, batch_id, manager, main_session_factory)
                continue
            if status != BatchStatus.COMPLETED.value:
                continue

            try:
                manager.retrieve_batch_results(batch_id)
            except Exception:
                logger.exception("Failed to retrieve results for batch %s", batch_id)
                continue

            completed = manager.get_completed_requests(agent_name=agent_name, batch_id=batch_id)
            if not completed:
                logger.warning("Batch %s reported completed but no requests found", batch_id)
                continue

            main_session = main_session_factory()
            try:
                result = apply_completed_requests(agent_name, completed, main_session, batch_id)
                main_session.commit()
                logger.info(
                    "Applied batch %s (%s): %s updated, %s failed",
                    batch_id,
                    agent_name,
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
