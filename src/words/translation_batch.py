"""Fill missing lemma translations through the OpenAI Batch API.

The synchronous populate path (``TranslationWorkflow.fix_missing_translations``)
makes one call per lemma per language group.  A backfill across thousands of
lemmas is better sent as a few OpenAI batches: one upload per batch, no worker
time, half the price.  This module builds the same requests -- through the same
``build_translation_prompt`` -- and submits them in batches of a bounded number
of lemmas, so a failed or slow batch holds back only its own slice.

Results are written by :func:`apply_populate_results`, which the Barsukas batch
poller calls automatically once a batch completes (``agents.common.batch
complete`` does the same by hand).
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    BatchRequestMetadata,
    BatchRequestStatus,
)
from clients.openai.batch_client import batch_response_text
from clients.openai.client import build_responses_request
from storage.crud.operation_log import log_translation_change
from storage.models.schema import Lemma
from storage.translation_helpers import (
    convert_llm_response_to_lang_codes,
    convert_llm_response_to_translation_metadata,
    get_reference_translation,
    get_translation,
    set_translation,
    split_llm_language_batches,
)
from wordfreq.translation.translations import TranslationPrompt, build_translation_prompt

logger = logging.getLogger(__name__)

AGENT_NAME = "voras"
OPERATION_TYPE = "populate_translations"
# The Responses API, as the synchronous client uses, so a batched request is
# the same request a live one would be.
BATCH_ENDPOINT = "/v1/responses"
DEFAULT_LEMMAS_PER_BATCH = 500

# A lemma with a request in any of these states is already being translated;
# planning it again would pay for the same words twice.
_IN_FLIGHT_STATUSES = (
    BatchRequestStatus.PENDING.value,
    BatchRequestStatus.QUEUED.value,
    BatchRequestStatus.SUBMITTED.value,
    BatchRequestStatus.PROCESSING.value,
)


@dataclass
class PopulateRequest:
    """One batch request: a lemma and the (at most 10) languages it asks for."""

    lemma_id: int
    languages: List[str]
    body: Dict[str, Any]


@dataclass
class PopulatePlan:
    """The requests a populate run would submit, and what it left out."""

    requests: List[PopulateRequest] = field(default_factory=list)
    lemmas_skipped_in_flight: int = 0
    lemmas_complete: int = 0

    @property
    def lemma_count(self) -> int:
        return len({request.lemma_id for request in self.requests})

    def missing_by_language(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for request in self.requests:
            for language_code in request.languages:
                counts[language_code] = counts.get(language_code, 0) + 1
        return counts


@dataclass
class SubmittedBatch:
    """One batch handed to OpenAI."""

    batch_id: str
    request_count: int
    lemma_count: int


def find_in_flight_lemma_ids(batch_session: Session) -> Set[int]:
    """Lemmas that already have an unfinished populate request."""
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


def build_request_body(prompt: TranslationPrompt, model: str) -> Dict[str, Any]:
    """Shape a translation prompt as a Responses API request.

    Delegates to ``build_responses_request``, the builder ``OpenAIClient.generate_chat``
    itself uses, so the batched request is the one a live call would send.
    """
    return build_responses_request(
        model, prompt.prompt, context=prompt.context, json_schema=prompt.schema
    )


def plan_populate_requests(
    session: Session,
    lemmas: Iterable[Lemma],
    languages: Sequence[str],
    model: str,
    in_flight_lemma_ids: Optional[Set[int]] = None,
) -> PopulatePlan:
    """Build a request for each lemma's missing languages, 10 languages at most per request.

    A lemma is asked only for the languages it lacks, so one run can mix
    lemmas that need nine languages with lemmas that need one.

    Args:
        session: Main database session.
        lemmas: Candidate lemmas.
        languages: Normalized target language codes.
        model: Model the requests will run on.
        in_flight_lemma_ids: Lemmas to skip because a batch is already
            translating them (see :func:`find_in_flight_lemma_ids`).
    """
    in_flight = in_flight_lemma_ids or set()
    plan = PopulatePlan()
    for lemma in lemmas:
        if lemma.id in in_flight:
            plan.lemmas_skipped_in_flight += 1
            continue
        missing = [
            language_code
            for language_code in languages
            if not (get_translation(session, lemma, language_code) or "").strip()
        ]
        if not missing:
            plan.lemmas_complete += 1
            continue

        reference_lang_code, reference_text = get_reference_translation(
            session, lemma, exclude_languages=missing
        )
        if not reference_lang_code or not reference_text:
            reference_lang_code, reference_text = "en", lemma.lemma_text

        for language_group in split_llm_language_batches(missing):
            prompt = build_translation_prompt(
                lemma.lemma_text,
                (reference_lang_code, reference_text),
                lemma.definition_text,
                lemma.pos_type,
                pos_subtype=lemma.pos_subtype,
                languages=language_group,
            )
            if prompt is None:
                logger.warning(
                    "Lemma %s (%s): could not build a prompt for %s",
                    lemma.id,
                    lemma.lemma_text,
                    ", ".join(language_group),
                )
                continue
            plan.requests.append(
                PopulateRequest(
                    lemma_id=lemma.id,
                    languages=language_group,
                    body=build_request_body(prompt, model),
                )
            )
    return plan


def chunk_by_lemma(
    requests: Sequence[PopulateRequest], lemmas_per_batch: int
) -> List[List[PopulateRequest]]:
    """Split requests into batches of at most ``lemmas_per_batch`` lemmas.

    A lemma's requests stay in one batch, so each lemma lands whole or not at all.
    """
    if lemmas_per_batch < 1:
        raise ValueError("lemmas_per_batch must be at least 1")
    chunks: List[List[PopulateRequest]] = []
    current: List[PopulateRequest] = []
    current_lemmas: Set[int] = set()
    for request in requests:
        if request.lemma_id not in current_lemmas and len(current_lemmas) >= lemmas_per_batch:
            chunks.append(current)
            current = []
            current_lemmas = set()
        current.append(request)
        current_lemmas.add(request.lemma_id)
    if current:
        chunks.append(current)
    return chunks


def submit_populate_batches(
    manager: BatchQueueManager,
    plan: PopulatePlan,
    lemmas_per_batch: int = DEFAULT_LEMMAS_PER_BATCH,
) -> List[SubmittedBatch]:
    """Queue and submit the plan as one OpenAI batch per ``lemmas_per_batch`` lemmas.

    Each batch is submitted as soon as it is queued.  If a submission fails,
    that batch's rows are marked cancelled and the error propagates; the
    batches already submitted stay in flight, and a rerun skips their lemmas.
    """
    submitted: List[SubmittedBatch] = []
    for chunk in chunk_by_lemma(plan.requests, lemmas_per_batch):
        records: List[BatchQueue] = []
        for request in chunk:
            custom_id = f"voras_populate_{request.lemma_id}_{uuid.uuid4().hex[:8]}"
            records.append(
                manager.queue_request(
                    custom_id=custom_id,
                    request_body=request.body,
                    metadata=BatchRequestMetadata(
                        custom_id=custom_id,
                        agent_name=AGENT_NAME,
                        operation_type=OPERATION_TYPE,
                        entity_id=request.lemma_id,
                        entity_type="lemma",
                    ),
                    endpoint=BATCH_ENDPOINT,
                )
            )
        try:
            batch_id, _file_id = manager.submit_batch(
                records,
                batch_metadata={"agent": AGENT_NAME, "operation": OPERATION_TYPE},
            )
        except Exception as exc:
            for record in records:
                record.status = BatchRequestStatus.CANCELLED.value
                record.error_message = f"Submission failed: {exc}"
            manager.db.commit()
            raise
        lemma_count = len({request.lemma_id for request in chunk})
        logger.info(
            "Submitted batch %s: %s request(s) for %s lemma(s)", batch_id, len(chunk), lemma_count
        )
        submitted.append(
            SubmittedBatch(batch_id=batch_id, request_count=len(chunk), lemma_count=lemma_count)
        )
    return submitted


def _response_text(response: Dict[str, Any]) -> str:
    """Pull the output text out of one stored Responses API batch result.

    Raises:
        ValueError: If the response was cut off or carries no text.
    """
    return batch_response_text(response)


def apply_populate_results(
    requests: Iterable[BatchQueue], session: Session, batch_id: str
) -> Dict[str, int]:
    """Write completed populate results to the main database.

    Only languages still missing are written: a translation added or edited
    by hand while the batch ran is left alone.  Each request commits on its
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
            structured = json.loads(_response_text(json.loads(request.response_body)))
            model = json.loads(request.request_body).get("model", "unknown")
            texts = convert_llm_response_to_lang_codes(structured)
            metadata = convert_llm_response_to_translation_metadata(structured)

            written = 0
            for language_code, raw_text in texts.items():
                text = (raw_text or "").strip()
                if not text:
                    continue
                if (get_translation(session, lemma, language_code) or "").strip():
                    continue
                language_metadata = metadata.get(language_code, {})
                old_translation, new_translation = set_translation(
                    session,
                    lemma,
                    language_code,
                    text,
                    translation_status=language_metadata.get("translation_status"),
                    translation_status_note=language_metadata.get("translation_status_note"),
                )
                log_translation_change(
                    session=session,
                    source=f"voras-agent/batch/{model}",
                    operation_type="translation",
                    lemma_id=lemma.id,
                    language_code=language_code,
                    old_translation=old_translation,
                    new_translation=new_translation,
                )
                written += 1
            session.commit()
            if written:
                results["updated"] += 1
                results["translations"] += written
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
