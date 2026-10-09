"""Legacy voras populate batches: applying the ones submitted before the staged job.

voras's ``--populate --batch`` now runs ``TRANSLATIONS_JOB``
(``workqueue.handlers.words.translations``) through ``workqueue.llm_batch``,
built from the same pieces as the live path (``words.translation_populate``).
Batches submitted before that carry no run id; the completion dispatchers
(``barsukas.batch_poller``, ``agents.common.batch``) route those rows here.
Once none are left in flight this module can go.
"""

import json
import logging
from typing import Any, Dict, Iterable, Set

from sqlalchemy.orm import Session

from clients.batch_queue import BatchQueue, BatchRequestStatus
from clients.openai.batch_client import batch_response_text
from storage.models.schema import Lemma
from storage.translation_helpers import convert_llm_response_to_lang_codes
from words.translation_populate import store_populated_translations

logger = logging.getLogger(__name__)

AGENT_NAME = "voras"
OPERATION_TYPE = "populate_translations"

# A lemma with a legacy request in any of these states is still being
# translated; a new run should not pay for the same words twice.
_IN_FLIGHT_STATUSES = (
    BatchRequestStatus.PENDING.value,
    BatchRequestStatus.QUEUED.value,
    BatchRequestStatus.SUBMITTED.value,
    BatchRequestStatus.PROCESSING.value,
)


def find_in_flight_lemma_ids(batch_session: Session) -> Set[int]:
    """Lemmas that still have an unfinished legacy populate request."""
    rows = (
        batch_session.query(BatchQueue.entity_id)
        .filter(
            BatchQueue.agent_name == AGENT_NAME,
            BatchQueue.operation_type == OPERATION_TYPE,
            BatchQueue.status.in_(_IN_FLIGHT_STATUSES),
        )
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def apply_populate_results(
    requests: Iterable[BatchQueue], session: Session, batch_id: str
) -> Dict[str, int]:
    """Write completed legacy populate results to the main database.

    Only languages still missing are written.  Each request commits on its
    own, so one bad response costs only its lemma.

    Returns:
        Counts: ``processed`` requests, ``updated`` (requests that wrote at
        least one translation), ``translations`` written, ``failed`` requests.
    """
    results = {"processed": 0, "updated": 0, "translations": 0, "failed": 0}
    for request in requests:
        results["processed"] += 1
        try:
            lemma = session.get(Lemma, request.entity_id) if request.entity_id else None
            if lemma is None:
                raise ValueError(f"Lemma {request.entity_id} not found")
            if not request.response_body:
                raise ValueError("No response body")
            structured: Dict[str, Any] = json.loads(
                batch_response_text(json.loads(request.response_body))
            )
            model = json.loads(request.request_body).get("model", "unknown")
            outcome = store_populated_translations(
                session,
                lemma,
                structured,
                list(convert_llm_response_to_lang_codes(structured)),
                source=f"voras-agent/batch/{model}",
                model=model,
            )
            session.commit()
            if outcome.written:
                results["updated"] += 1
                results["translations"] += len(outcome.written)
        except Exception as exc:
            session.rollback()
            results["failed"] += 1
            logger.error(
                "Failed to apply populate result %s (batch %s): %s",
                request.custom_id,
                batch_id,
                exc,
            )
    return results
