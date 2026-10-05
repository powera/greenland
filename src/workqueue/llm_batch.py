"""Run staged LLM jobs inline or through the OpenAI Batch API.

A *job* is up to three *stages*.  Each stage is two plain functions:

* ``prepare(session, state, ctx)`` reads the database and returns an
  ``LLMCall`` to make, a ``Ready`` answer that needs no model (a copy from a
  sibling language, say), or ``Done`` to stop (nothing to do, or invalid).
  It never writes.
* ``apply(session, state, data, ctx)`` takes the model's structured answer,
  writes what it should, and returns ``Done``, or ``Next(state)`` to carry the
  item on to the following stage.

The glue here runs a job two ways with the same semantics:

* :func:`run_inline` makes each call live, stage by stage.  One word is a job
  over one item; this is the interactive path.
* :func:`start_batch_run` queues stage one as OpenAI batches;
  :func:`complete_rows` applies each finished batch and :func:`advance_run`
  starts the next stage.

Both runners treat a stage as a barrier: no item starts stage N+1 until every
item of the run has finished stage N (applied, rejected or failed).  Stage N+1
is prepared only then, so its prompts read what stage N wrote for *all* items.

Batch progress lives on the ``BatchQueue`` rows in the batch-tracking database;
there are no other tables.  A row's ``custom_id`` is
``{job}:{run_id}:{stage_index}:{item_key}:{uuid8}`` and its ``extra`` metadata
holds the run id, the item state, the model, and once applied, the outcome and
any ``next_state``.  ``advanced`` marks a row whose next stage has been sent,
which makes advancing safe to repeat.

Completion is driven from the Barsukas batch poller and from
``python -m agents.common.batch complete``, which look the job up in
``workqueue.registry.LLM_JOBS`` by the rows' ``agent_name``.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from sqlalchemy.orm import Session, object_session

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    BatchRequestMetadata,
    BatchRequestStatus,
    request_extra,
    update_request_extra,
)
from clients.lib import LLMCallsDisabledError
from clients.openai.batch_client import batch_response_text
from clients.openai.client import build_responses_request
from clients.types import LLMCall

if TYPE_CHECKING:
    from clients.unified_client import UnifiedLLMClient

logger = logging.getLogger(__name__)

MAX_STAGES = 3
BATCH_ENDPOINT = "/v1/responses"
DEFAULT_ITEMS_PER_BATCH = 500

# Rows OpenAI has not answered yet.
_OPEN_STATUSES = (
    BatchRequestStatus.PENDING.value,
    BatchRequestStatus.QUEUED.value,
    BatchRequestStatus.SUBMITTED.value,
    BatchRequestStatus.PROCESSING.value,
)

DoneStatus = Literal["written", "skipped", "rejected", "failed"]


@dataclass(frozen=True)
class Done:
    """The item is finished.  ``written`` means apply saved something."""

    status: DoneStatus
    detail: str = ""


@dataclass(frozen=True)
class Next:
    """Carry the item to the following stage once the barrier opens."""

    state: Dict[str, Any]


@dataclass(frozen=True)
class Ready:
    """An answer that needed no model; it goes through ``apply`` like one that did."""

    data: Dict[str, Any]


@dataclass(frozen=True)
class StageContext:
    """What a stage may want to know about how it is being run."""

    model: str
    via: Literal["inline", "batch"]


PrepareOutcome = Union[LLMCall, Ready, Done]
ApplyOutcome = Union[Done, Next]
PrepareFn = Callable[[Session, Dict[str, Any], StageContext], PrepareOutcome]
ApplyFn = Callable[[Session, Dict[str, Any], Dict[str, Any], StageContext], ApplyOutcome]


@dataclass(frozen=True)
class Stage:
    name: str
    prepare: PrepareFn
    apply: ApplyFn


@dataclass(frozen=True)
class Job:
    """A named sequence of one to three stages.

    Attributes:
        name: Also the ``agent_name`` on the job's batch rows; no ``:``.
        stages: Run in order; ``Next`` from the last stage is an error.
        item_key: Identifies an item for deduplication across runs, e.g.
            ``"123:fr:grammatical_gender"``.
        entity_type / entity_id_key: Recorded on batch rows for browsing; the
            id is read from the item state under ``entity_id_key``.
    """

    name: str
    stages: Tuple[Stage, ...]
    item_key: Callable[[Dict[str, Any]], str]
    entity_type: str = "lemma"
    entity_id_key: str = "lemma_id"

    def __post_init__(self) -> None:
        if not 1 <= len(self.stages) <= MAX_STAGES:
            raise ValueError(f"Job {self.name!r} needs 1-{MAX_STAGES} stages")
        if ":" in self.name:
            raise ValueError(f"Job name {self.name!r} may not contain ':'")
        names = [stage.name for stage in self.stages]
        if len(set(names)) != len(names):
            raise ValueError(f"Job {self.name!r} has duplicate stage names")

    def stage_index(self, stage_name: str) -> int:
        for index, stage in enumerate(self.stages):
            if stage.name == stage_name:
                return index
        raise KeyError(f"Job {self.name!r} has no stage {stage_name!r}")


# ---------------------------------------------------------------------------
# Inline
# ---------------------------------------------------------------------------


def run_inline(
    session: Session,
    job: Job,
    states: Sequence[Dict[str, Any]],
    client: "UnifiedLLMClient",
    model: str,
) -> List[Done]:
    """Run *job* over *states* with live calls, stage by stage.

    Commits after each item.  An item that fails is rolled back and reported
    as ``Done("failed")``; the others carry on.  ``LLMCallsDisabledError`` is
    re-raised: a run under a kill switch should stop, not report every item
    as failed.

    Returns:
        One ``Done`` per input state, in order.
    """
    ctx = StageContext(model=model, via="inline")
    finished: Dict[int, Done] = {}
    pending: List[Tuple[int, Dict[str, Any]]] = list(enumerate(states))
    for stage in job.stages:
        carried: List[Tuple[int, Dict[str, Any]]] = []
        for index, state in pending:
            outcome = _run_stage_inline(session, stage, state, client, ctx)
            if isinstance(outcome, Next):
                carried.append((index, outcome.state))
            else:
                finished[index] = outcome
        pending = carried
    for index, _state in pending:
        finished[index] = Done("failed", f"{job.stages[-1].name} returned Next from the last stage")
    return [finished[index] for index in range(len(states))]


def _run_stage_inline(
    session: Session,
    stage: Stage,
    state: Dict[str, Any],
    client: "UnifiedLLMClient",
    ctx: StageContext,
) -> ApplyOutcome:
    try:
        prepared = stage.prepare(session, state, ctx)
        if isinstance(prepared, Done):
            return prepared
        if isinstance(prepared, Ready):
            data = prepared.data
        else:
            response = client.generate_chat(model=ctx.model, **prepared.chat_kwargs())
            data = response.structured_data
        outcome = stage.apply(session, state, data, ctx)
        session.commit()
        return outcome
    except LLMCallsDisabledError:
        session.rollback()
        raise
    except Exception as exc:
        session.rollback()
        logger.error("Stage %s failed for %s: %s", stage.name, state, exc)
        return Done("failed", str(exc))


# ---------------------------------------------------------------------------
# Batch: start
# ---------------------------------------------------------------------------


@dataclass
class RunReport:
    """What :func:`start_batch_run` found and sent."""

    run_id: str
    job_name: str
    items: int = 0
    skipped_in_flight: int = 0
    calls: int = 0
    resolved_without_llm: Counter[str] = field(default_factory=Counter)
    batch_ids: List[str] = field(default_factory=list)
    dry_run: bool = False


def start_batch_run(
    session: Session,
    manager: BatchQueueManager,
    job: Job,
    states: Sequence[Dict[str, Any]],
    model: str,
    items_per_batch: int = DEFAULT_ITEMS_PER_BATCH,
    dry_run: bool = False,
) -> RunReport:
    """Prepare stage one for every item and submit the calls as OpenAI batches.

    Items already open in another run of this job are skipped, as are
    duplicate items.  Answers that need no model (``Ready``) are applied at
    once; ``Done`` outcomes are only counted.  With ``dry_run`` nothing is
    written or submitted, and ``Ready`` answers are counted, not applied.

    Raises:
        Exception: From a failed submission, after that chunk's rows are
            cancelled.  Chunks already submitted stay in flight, and a rerun
            skips their items.
    """
    report = RunReport(run_id=uuid.uuid4().hex[:12], job_name=job.name, dry_run=dry_run)
    ctx = StageContext(model=model, via="batch")
    stage = job.stages[0]
    open_keys = open_item_keys(manager, job)
    seen: Set[str] = set()
    calls: List[Tuple[str, Dict[str, Any], LLMCall]] = []
    carried: List[Tuple[str, Dict[str, Any]]] = []

    for state in states:
        report.items += 1
        key = job.item_key(state)
        if key in open_keys or key in seen:
            report.skipped_in_flight += 1
            continue
        seen.add(key)
        prepared = stage.prepare(session, state, ctx)
        if isinstance(prepared, LLMCall):
            calls.append((key, state, prepared))
            continue
        if isinstance(prepared, Done):
            report.resolved_without_llm[prepared.status] += 1
            continue
        if dry_run:
            report.resolved_without_llm["answered"] += 1
            continue
        outcome = _apply_ready(session, stage, state, prepared, ctx)
        if isinstance(outcome, Next):
            carried.append((key, outcome.state))
            report.resolved_without_llm["carried"] += 1
        else:
            report.resolved_without_llm[outcome.status] += 1

    report.calls = len(calls)
    if dry_run:
        return report

    for key, next_state in carried:
        _record_carried(manager, job, report.run_id, 0, key, next_state, model, items_per_batch)
    report.batch_ids = _submit_calls(manager, job, report.run_id, 0, calls, model, items_per_batch)
    if not calls and carried:
        advance_run(job, report.run_id, manager, session)
    return report


def open_item_keys(manager: BatchQueueManager, job: Job) -> Set[str]:
    """Item keys of *job* that some run has not finished with."""
    rows = manager.db.query(BatchQueue).filter(BatchQueue.agent_name == job.name).all()
    keys: Set[str] = set()
    for row in rows:
        extra = request_extra(row)
        if "item_key" not in extra:
            continue
        if _row_is_open(row, extra) or (
            extra.get("next_state") is not None and not extra.get("advanced")
        ):
            keys.add(str(extra["item_key"]))
    return keys


def _row_is_open(row: BatchQueue, extra: Dict[str, Any]) -> bool:
    """Not yet answered, or answered but not yet applied."""
    if row.status in _OPEN_STATUSES:
        return True
    return row.status == BatchRequestStatus.COMPLETED.value and not extra.get("applied")


def _apply_ready(
    session: Session, stage: Stage, state: Dict[str, Any], ready: Ready, ctx: StageContext
) -> ApplyOutcome:
    try:
        outcome = stage.apply(session, state, ready.data, ctx)
        session.commit()
        return outcome
    except Exception as exc:
        session.rollback()
        logger.error("Stage %s failed for %s: %s", stage.name, state, exc)
        return Done("failed", str(exc))


def _custom_id(job: Job, run_id: str, stage_index: int, key: str) -> str:
    return f"{job.name}:{run_id}:{stage_index}:{key}:{uuid.uuid4().hex[:8]}"


def _metadata(
    job: Job, custom_id: str, stage: Stage, state: Dict[str, Any], extra: Dict[str, Any]
) -> BatchRequestMetadata:
    entity_id = state.get(job.entity_id_key)
    return BatchRequestMetadata(
        custom_id=custom_id,
        agent_name=job.name,
        operation_type=stage.name,
        entity_id=entity_id if isinstance(entity_id, int) else None,
        entity_type=job.entity_type,
        language_code=state.get("language_code"),
        extra=extra,
    )


def _record_carried(
    manager: BatchQueueManager,
    job: Job,
    run_id: str,
    stage_index: int,
    key: str,
    next_state: Dict[str, Any],
    model: str,
    items_per_batch: int,
) -> None:
    """Store an item that finished a stage without a model call and goes on.

    It has no batch to ride on, so it gets a row of its own, already applied,
    for :func:`advance_run` to pick up like any other.
    """
    stage = job.stages[stage_index]
    custom_id = _custom_id(job, run_id, stage_index, key)
    row = manager.queue_request(
        custom_id=custom_id,
        request_body={},
        metadata=_metadata(
            job,
            custom_id,
            stage,
            next_state,
            {
                "run_id": run_id,
                "item_key": key,
                "state": next_state,
                "model": model,
                "items_per_batch": items_per_batch,
                "applied": True,
                "outcome": "next",
                "next_state": next_state,
                "without_llm": True,
            },
        ),
        endpoint=BATCH_ENDPOINT,
    )
    row.status = BatchRequestStatus.COMPLETED.value
    manager.db.commit()


def _submit_calls(
    manager: BatchQueueManager,
    job: Job,
    run_id: str,
    stage_index: int,
    calls: Sequence[Tuple[str, Dict[str, Any], LLMCall]],
    model: str,
    items_per_batch: int,
) -> List[str]:
    """Queue *calls* as rows and submit them, ``items_per_batch`` to a batch."""
    if items_per_batch < 1:
        raise ValueError("items_per_batch must be at least 1")
    stage = job.stages[stage_index]
    batch_ids: List[str] = []
    for start in range(0, len(calls), items_per_batch):
        chunk = calls[start : start + items_per_batch]
        rows: List[BatchQueue] = []
        for key, state, call in chunk:
            custom_id = _custom_id(job, run_id, stage_index, key)
            body = build_responses_request(
                model,
                call.prompt,
                context=call.context,
                json_schema=call.schema,
                max_tokens=call.max_tokens,
            )
            rows.append(
                manager.queue_request(
                    custom_id=custom_id,
                    request_body=body,
                    metadata=_metadata(
                        job,
                        custom_id,
                        stage,
                        state,
                        {
                            "run_id": run_id,
                            "item_key": key,
                            "state": state,
                            "model": model,
                            "items_per_batch": items_per_batch,
                        },
                    ),
                    endpoint=BATCH_ENDPOINT,
                )
            )
        try:
            batch_id, _file_id = manager.submit_batch(
                rows,
                batch_metadata={"agent": job.name, "run": run_id, "stage": stage.name},
            )
        except Exception as exc:
            for row in rows:
                row.status = BatchRequestStatus.CANCELLED.value
                row.error_message = f"Submission failed: {exc}"
            manager.db.commit()
            raise
        logger.info(
            "Submitted batch %s: %s %s call(s) for run %s", batch_id, len(rows), stage.name, run_id
        )
        batch_ids.append(batch_id)
    return batch_ids


# ---------------------------------------------------------------------------
# Batch: completion and the barrier
# ---------------------------------------------------------------------------


def complete_rows(
    job: Job,
    requests: Iterable[BatchQueue],
    session: Session,
    batch_id: str,
    manager: Optional[BatchQueueManager] = None,
) -> Dict[str, int]:
    """Apply a finished batch's rows, then advance every run they belong to.

    Rows already applied are skipped, so completing a batch twice is safe.
    Each row commits on its own; a bad response costs only its item.  Rows of
    this batch that OpenAI never answered are marked failed, so they cannot
    hold the barrier shut.

    Args:
        job: The job the rows belong to.
        requests: Completed rows (attached to the batch-tracking session).
        session: Main database session.
        batch_id: For logs, and to find unanswered rows.
        manager: Used to submit a next stage; built on the rows' session if
            omitted.

    Returns:
        Counts: ``processed``, ``updated`` (rows that wrote), ``skipped``
        (rejected or nothing to do), ``failed``, ``carried`` (going on to the
        next stage) and ``next_stage_calls`` submitted.
    """
    rows = list(requests)
    results = {
        "processed": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "carried": 0,
        "next_stage_calls": 0,
    }
    if manager is None:
        if not rows:
            return results
        batch_session = object_session(rows[0])
        if batch_session is None:
            raise ValueError("Batch rows are not attached to a session")
        manager = BatchQueueManager(batch_session)

    _fail_unanswered_rows(manager, batch_id)
    run_ids: Set[str] = set()
    for row in rows:
        extra = request_extra(row)
        if extra.get("applied") or "run_id" not in extra:
            continue
        run_ids.add(str(extra["run_id"]))
        results["processed"] += 1
        outcome = _apply_row(job, row, extra, session, batch_id)
        _record_outcome(row, outcome, is_last_stage=_is_last_stage(job, row))
        manager.db.commit()
        if isinstance(outcome, Next) and not _is_last_stage(job, row):
            results["carried"] += 1
        elif isinstance(outcome, Done) and outcome.status == "written":
            results["updated"] += 1
        elif isinstance(outcome, Done) and outcome.status in ("skipped", "rejected"):
            results["skipped"] += 1
        else:
            results["failed"] += 1

    for run_id in sorted(run_ids):
        results["next_stage_calls"] += advance_run(job, run_id, manager, session)
    return results


def _is_last_stage(job: Job, row: BatchQueue) -> bool:
    return job.stage_index(row.operation_type) == len(job.stages) - 1


def _apply_row(
    job: Job, row: BatchQueue, extra: Dict[str, Any], session: Session, batch_id: str
) -> ApplyOutcome:
    try:
        stage = job.stages[job.stage_index(row.operation_type)]
        if not row.response_body:
            raise ValueError("No response body")
        data = json.loads(batch_response_text(json.loads(row.response_body)))
        model = str(extra.get("model") or json.loads(row.request_body).get("model", "unknown"))
        outcome = stage.apply(session, dict(extra["state"]), data, StageContext(model, "batch"))
        session.commit()
        return outcome
    except Exception as exc:
        session.rollback()
        logger.error("Failed to apply %s (batch %s): %s", row.custom_id, batch_id, exc)
        return Done("failed", str(exc))


def _record_outcome(row: BatchQueue, outcome: ApplyOutcome, is_last_stage: bool) -> None:
    if isinstance(outcome, Next) and not is_last_stage:
        update_request_extra(row, applied=True, outcome="next", next_state=outcome.state)
    elif isinstance(outcome, Next):
        update_request_extra(
            row, applied=True, outcome="failed", detail="Next returned from the last stage"
        )
    else:
        update_request_extra(row, applied=True, outcome=outcome.status, detail=outcome.detail)


def _fail_unanswered_rows(manager: BatchQueueManager, batch_id: str) -> None:
    """Mark rows of a completed batch that got no result line as failed."""
    unanswered = (
        manager.db.query(BatchQueue)
        .filter(BatchQueue.batch_id == batch_id, BatchQueue.status.in_(_OPEN_STATUSES))
        .all()
    )
    for row in unanswered:
        row.status = BatchRequestStatus.FAILED.value
        row.error_message = "No result in the completed batch"
    if unanswered:
        manager.db.commit()


def fail_batch(job: Job, batch_id: str, manager: BatchQueueManager, session: Session) -> int:
    """Handle a batch that ended failed, expired or cancelled.

    Its rows count as finished, so the barrier can open for the rest of each
    run.  Returns the number of next-stage calls this submitted.
    """
    rows = manager.db.query(BatchQueue).filter(BatchQueue.batch_id == batch_id).all()
    for row in rows:
        if row.status in _OPEN_STATUSES:
            row.status = BatchRequestStatus.FAILED.value
            row.error_message = row.error_message or "Batch did not complete"
    manager.db.commit()
    run_ids = {str(request_extra(row)["run_id"]) for row in rows if "run_id" in request_extra(row)}
    return sum(advance_run(job, run_id, manager, session) for run_id in sorted(run_ids))


def advance_run(job: Job, run_id: str, manager: BatchQueueManager, session: Session) -> int:
    """Start the next stage of a run if every item has finished this one.

    Safe to call at any time and repeatedly: it does nothing while any row of
    the run is open, and a row is marked ``advanced`` once its next stage is
    sent.  Next-stage ``prepare`` runs here, against the database as the
    previous stage left it.

    Returns:
        The number of calls submitted.
    """
    submitted = 0
    # Each pass moves the run on by one stage; Ready answers can carry an item
    # through a stage without a batch, so loop until a batch is out or the run
    # has nothing left.
    for _ in range(MAX_STAGES):
        rows = manager.get_requests_by_custom_id_prefix(f"{job.name}:{run_id}:")
        extras = [(row, request_extra(row)) for row in rows]
        if any(_row_is_open(row, extra) for row, extra in extras):
            return submitted
        waiting = [
            (row, extra)
            for row, extra in extras
            if extra.get("next_state") is not None and not extra.get("advanced")
        ]
        if not waiting:
            return submitted
        calls_sent, carried_any = _start_next_stage(job, run_id, waiting, manager, session)
        submitted += calls_sent
        if calls_sent:
            return submitted
        if not carried_any:
            return submitted
    return submitted


def _start_next_stage(
    job: Job,
    run_id: str,
    waiting: Sequence[Tuple[BatchQueue, Dict[str, Any]]],
    manager: BatchQueueManager,
    session: Session,
) -> Tuple[int, bool]:
    """Prepare and submit the next stage for *waiting* rows.

    Returns:
        ``(calls submitted, whether any item was carried on without a call)``.
    """
    by_stage: Dict[int, List[Tuple[BatchQueue, Dict[str, Any]]]] = {}
    for row, extra in waiting:
        by_stage.setdefault(job.stage_index(row.operation_type) + 1, []).append((row, extra))

    calls_sent = 0
    carried_any = False
    for stage_index, group in sorted(by_stage.items()):
        stage = job.stages[stage_index]
        model = str(group[0][1].get("model") or "")
        items_per_batch = int(group[0][1].get("items_per_batch") or DEFAULT_ITEMS_PER_BATCH)
        ctx = StageContext(model=model, via="batch")
        calls: List[Tuple[str, Dict[str, Any], LLMCall]] = []
        for row, extra in group:
            key = str(extra["item_key"])
            state = dict(extra["next_state"])
            try:
                prepared = stage.prepare(session, state, ctx)
            except Exception as exc:
                logger.error("Stage %s prepare failed for %s: %s", stage.name, state, exc)
                update_request_extra(row, next_outcome="failed", next_detail=str(exc))
                continue
            if isinstance(prepared, Done):
                update_request_extra(row, next_outcome=prepared.status, next_detail=prepared.detail)
            if isinstance(prepared, LLMCall):
                calls.append((key, state, prepared))
            elif isinstance(prepared, Ready):
                outcome = _apply_ready(session, stage, state, prepared, ctx)
                if isinstance(outcome, Next) and stage_index < len(job.stages) - 1:
                    _record_carried(
                        manager,
                        job,
                        run_id,
                        stage_index,
                        key,
                        outcome.state,
                        model,
                        items_per_batch,
                    )
                    carried_any = True
                else:
                    detail = outcome.detail if isinstance(outcome, Done) else ""
                    status = outcome.status if isinstance(outcome, Done) else "failed"
                    update_request_extra(row, next_outcome=status, next_detail=detail)
        _submit_calls(manager, job, run_id, stage_index, calls, model, items_per_batch)
        calls_sent += len(calls)
        for row, _extra in group:
            update_request_extra(row, advanced=True)
        manager.db.commit()
    return calls_sent, carried_any
