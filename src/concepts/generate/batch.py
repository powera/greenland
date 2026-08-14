"""Batch-API preparation and completion for concept bodies.

Generating concept bodies through the OpenAI Batch API costs roughly half of
what synchronous generation costs, at the price of a two-step flow:

1. *Preparation* (:func:`submit_concept_body_batch`) fetches every Wikidata
   seed up front, builds one ``/v1/chat/completions`` request per resolvable
   Q-id, and stashes the seed alongside its request. All requests go out as a
   single batch.
2. *Completion* (:func:`complete_concept_body_batch`) creates the concepts from
   the generated bodies plus the stashed seeds, so no outbound Wikimedia call
   is needed a second time.

Both steps are shared by every agent that queues concept bodies (``voverukas``
discovers its Q-ids by ranking, ``voveraite`` is handed them).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Sequence

from clients.batch_queue import BatchRequestMetadata, get_batch_manager
from concepts.generate.entry import ConceptEntryGenerator
from concepts.persist import create_concept_from_seed
from concepts.seed.wikidata_query import query_wikidata_seed
from storage.backend import create_session as create_backend_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.concept import cache_wikidata_title
from storage.wikidata import WikidataConceptSeed, normalize_qid

logger = logging.getLogger(__name__)

__all__ = [
    "BATCH_OPERATION",
    "ConceptBatchRequest",
    "ConceptBatchSubmission",
    "complete_concept_body_batch",
    "completion_command_hint",
    "submit_concept_body_batch",
]

# Operation type recorded on queued batch requests; the completion handler in
# agents/common/batch.py dispatches on the agent name plus this operation.
BATCH_OPERATION: str = "generate_concept"


@dataclass(frozen=True)
class ConceptBatchRequest:
    """One topic to queue for body generation.

    Attributes:
        qid: The resolved Wikidata Q-id, or None when the topic could not be
            resolved (counted as skipped).
        title: Display title for logging. When set it is also the title cached
            for the Q-id, preserving the exact title that resolved to it;
            otherwise the seed's own title is cached.
    """

    qid: Optional[str]
    title: str = ""


@dataclass(frozen=True)
class ConceptBatchSubmission:
    """What one submission attempt queued and sent."""

    batch_id: Optional[str]
    queued: int
    skipped: int


def submit_concept_body_batch(
    config: DataSourceConfig,
    requests: Sequence[ConceptBatchRequest],
    *,
    agent_name: str,
) -> ConceptBatchSubmission:
    """Queue concept-body generation for every request as one Batch API job.

    Args:
        config: Backend, model, and debug settings. A model is required.
        requests: Topics to generate bodies for.
        agent_name: Agent name recorded on each queued request; the completion
            step dispatches on it.

    Returns:
        A :class:`ConceptBatchSubmission` describing what was submitted.

    Raises:
        ValueError: If no model is configured.
    """
    generator = ConceptEntryGenerator(config)
    if not generator.model:
        raise ValueError("A model is required to submit a batch (set --model).")

    batch_manager = get_batch_manager(debug=config.debug)
    session = create_backend_session(config)
    queued = 0
    skipped = 0
    try:
        for request in requests:
            qid = normalize_qid(request.qid) if request.qid else None
            if qid is None:
                logger.info("SKIP (unresolved) %s", request.title or request.qid)
                skipped += 1
                continue

            seed = query_wikidata_seed(qid, include_regional_wikis=True)
            if seed is None:
                logger.info("SKIP (no seed) [%s] %s", qid, request.title)
                skipped += 1
                continue

            # Cache the qid<->title mapping regardless of batch success.
            cache_wikidata_title(session, qid, request.title or seed.title)

            request_body = generator.build_request_body(
                seed.title, seed.summary, list(seed.sources)
            )

            custom_id = f"{agent_name}_{seed.qid}"
            metadata = BatchRequestMetadata(
                custom_id=custom_id,
                agent_name=agent_name,
                operation_type=BATCH_OPERATION,
                entity_type="concept",
            )
            try:
                record = batch_manager.queue_request(
                    custom_id=custom_id,
                    request_body=request_body,
                    metadata=metadata,
                    endpoint="/v1/chat/completions",
                )
            except ValueError as exc:
                logger.info("SKIP (already queued) [%s] %s: %s", qid, seed.title, exc)
                skipped += 1
                continue

            # Stash the full seed + model so the completion step can build the
            # concept from the same inputs without a second fetch.
            record.additional_metadata = json.dumps(
                {
                    **metadata.to_dict(),
                    "qid": seed.qid,
                    "seed": {
                        "qid": seed.qid,
                        "title": seed.title,
                        "summary": seed.summary,
                        "sources": list(seed.sources),
                    },
                    "source_model": generator.model,
                },
                ensure_ascii=False,
            )
            batch_manager.db.commit()
            logger.info("QUEUED [%s] %s", qid, seed.title)
            queued += 1

        if queued == 0:
            logger.info("Nothing to submit (queued 0 requests).")
            return ConceptBatchSubmission(batch_id=None, queued=0, skipped=skipped)

        pending = batch_manager.get_pending_requests(
            agent_name=agent_name, operation_type=BATCH_OPERATION
        )
        batch_id, _file_id = batch_manager.submit_batch(
            pending,
            batch_metadata={"agent": agent_name, "operation": BATCH_OPERATION},
        )
        logger.info("Submitted batch %s with %d requests", batch_id, len(pending))
        logger.info(
            "Complete it later with: %s", completion_command_hint(config, batch_id, agent_name)
        )
        return ConceptBatchSubmission(batch_id=batch_id, queued=queued, skipped=skipped)
    finally:
        session.close()


def completion_command_hint(config: DataSourceConfig, batch_id: str, agent_name: str) -> str:
    """Return the command that completes a submitted batch on this backend."""
    backend_flag = ""
    if config.backend_type == BackendType.POSTGRES:
        backend_flag = " --postgres"
    elif config.backend_type == BackendType.JSONL:
        backend_flag = " --backend jsonl"
    return (
        "PYTHONPATH=src python src/agents/common/batch.py complete "
        f"--batch-id {batch_id} --agent {agent_name}{backend_flag}"
    )


def _extract_chat_completion_text(response_body: Optional[str]) -> Optional[str]:
    """Pull the assistant message text out of a stored batch response body."""
    if not response_body:
        return None
    try:
        response = json.loads(response_body)
    except json.JSONDecodeError:
        return None

    body = response.get("body") if isinstance(response.get("body"), dict) else response
    choices = body.get("choices") if isinstance(body, dict) else None
    if not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content.strip() if isinstance(content, str) else None


def complete_concept_body_batch(
    requests: Iterable[Any], session: Any, batch_id: str
) -> Dict[str, int]:
    """Create concepts from stashed (seed + generated body) batch results.

    Each request stashed the full Wikidata seed and model in its metadata at
    submit time, so concept creation needs no further outbound calls: the body
    is the LLM output, the seed is the stored input.

    Args:
        requests: Completed ``BatchQueue`` records for a concept-body agent.
        session: Database session.
        batch_id: The batch ID (for logging only).

    Returns:
        ``{"processed", "created", "skipped", "failed"}`` counts.
    """
    results = {"processed": 0, "created": 0, "skipped": 0, "failed": 0}

    for req in requests:
        results["processed"] += 1
        try:
            metadata = json.loads(req.additional_metadata) if req.additional_metadata else {}
            seed_data = metadata.get("seed")
            if not seed_data:
                logger.warning("No stashed seed for request %s; skipping", req.custom_id)
                results["failed"] += 1
                continue

            body = _extract_chat_completion_text(req.response_body)
            if not body:
                logger.warning("No generated body for request %s; skipping", req.custom_id)
                results["failed"] += 1
                continue

            seed = WikidataConceptSeed(
                qid=seed_data["qid"],
                title=seed_data["title"],
                summary=seed_data.get("summary", ""),
                sources=list(seed_data.get("sources", [])),
            )
            result = create_concept_from_seed(
                session,
                seed,
                body=body,
                source_model=metadata.get("source_model"),
            )
            if result.status == "created":
                session.commit()
                results["created"] += 1
            else:
                # "exists" / "unresolved" / "failed" — nothing persisted.
                results["skipped" if result.status == "exists" else "failed"] += 1
            logger.info(
                "%s [%s] %s%s",
                result.status.upper(),
                seed.qid,
                seed.title,
                f" - {result.detail}" if result.detail else "",
            )
        except Exception as exc:
            session.rollback()
            results["failed"] += 1
            logger.error(
                "Failed to create concept for request %s (batch %s): %s",
                req.custom_id,
                batch_id,
                exc,
            )

    return results
