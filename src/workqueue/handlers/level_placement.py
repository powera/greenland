"""Sense placement as a regular Barsukas-visible staged batch job."""

import json
from typing import Any

from sqlalchemy.orm import Session

from clients.lib import schema_from_dict
from clients.types import LLMCall
from quality.curriculum_review import checked_suggestion, fingerprint
from reports.curriculum_bands import PlannedMove, apply_moves, RankEvidence, effective_rank
from reports.level_candidates import IndexRow, LevelIndex, query_for_lemma
from storage.backend import BackendType, DataSourceConfig
from storage.backup import create_backup
from storage.crud.operation_log import log_entity_operation
from storage.models.operation_log import OperationLog
from storage.models.schema import Lemma
from wordfreq.data.cohorts import COHORT_LEVELS
from wordfreq.frequency.combined_rank import lemmas_without_corpus_evidence
from workqueue.llm_batch import Done, Job, Stage, StageContext


def _source(state: dict[str, Any]) -> str:
    return "curriculum-review/results/" + str(state["review_id"])


def _current_fingerprint(session: Session, lemma: Lemma) -> str:
    # Match load_level_index's effective rank, including tier-only/unranked senses.
    rows: list[IndexRow] = []
    if lemma.difficulty_level is not None and lemma.difficulty_level > 0:
        evidence = RankEvidence(
            no_corpus_ids=frozenset(lemmas_without_corpus_evidence(session, [lemma.id]))
        )
        rows.append(
            IndexRow(
                lemma.id,
                lemma.pos_type,
                lemma.pos_subtype,
                lemma.difficulty_level,
                effective_rank(lemma, evidence),
            )
        )
    return fingerprint(lemma, query_for_lemma(session, lemma, LevelIndex(rows, {})))


def _receipt(session: Session, state: dict[str, Any]) -> OperationLog | None:
    return (
        session.query(OperationLog)
        .filter(
            OperationLog.source == _source(state),
            OperationLog.entity_guid == state["record"]["guid"],
            OperationLog.operation_type == "curriculum_placement_applied",
        )
        .order_by(OperationLog.id.desc())
        .first()
    )


def _already_applied(session: Session, state: dict[str, Any], lemma: Lemma) -> bool:
    receipt = _receipt(session, state)
    if receipt is None:
        return False
    fact = json.loads(receipt.fact)
    return bool(
        fact.get("original_fingerprint") == state["record"]["fingerprint"]
        and fact.get("applied_fingerprint") == _current_fingerprint(session, lemma)
    )


def _prepare(session: Session, state: dict[str, Any], ctx: StageContext) -> LLMCall | Done:
    record = state["record"]
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None or lemma.guid != record["guid"]:
        return Done("rejected", "Sense is missing or identity changed")
    if _already_applied(session, state, lemma):
        return Done("skipped", "Placement already applied")
    if _current_fingerprint(session, lemma) != record["fingerprint"]:
        return Done("rejected", "Stale sense or evidence before submission")
    body = record["request"]["body"]
    if body["model"] != ctx.model:
        raise ValueError("Prepared model differs from submission model")
    messages = body["input"]
    return LLMCall(
        prompt=messages[1]["content"],
        context=messages[0]["content"],
        schema=schema_from_dict(body["text"]["format"]["schema"]),
        max_tokens=body["max_output_tokens"],
    )


def _backup_once(session: Session, state: dict[str, Any]) -> None:
    """One minor backup per planned chunk, with its receipt in the move transaction."""
    source = "curriculum-review/backup/" + str(state["review_id"])
    markers = (
        session.query(OperationLog)
        .filter(
            OperationLog.source == source,
            OperationLog.operation_type == "curriculum_review_backup",
        )
        .all()
    )
    if any(json.loads(marker.fact).get("group") == state["backup_group"] for marker in markers):
        return
    database = session.get_bind().engine.url.database
    if not database or database == ":memory:":
        raise ValueError("Applying placements requires a persistent SQLite database")
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=database)
    backup = create_backup(config, "curriculum-batch", tier="minor")
    log_entity_operation(
        session,
        source=source,
        operation_type="curriculum_review_backup",
        fact=dict(group=state["backup_group"], path=str(backup), tier="minor"),
    )


def _apply(
    session: Session, state: dict[str, Any], data: dict[str, Any], ctx: StageContext
) -> Done:
    record = state["record"]
    suggestion = checked_suggestion(data, record)
    if session.get_bind().dialect.name != "sqlite":
        raise ValueError("Curriculum review currently supports SQLite application only")
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    lemma = (
        session.query(Lemma).filter(Lemma.id == state["lemma_id"]).populate_existing().one_or_none()
    )
    if lemma is None or lemma.guid != record["guid"]:
        return Done("rejected", "Sense is missing or identity changed")
    if _already_applied(session, state, lemma):
        return Done("skipped", "Placement already applied")
    source = _source(state)
    log_entity_operation(
        session,
        source=source,
        operation_type="curriculum_placement_suggestion",
        entity_guid=lemma.guid,
        lemma_id=lemma.id,
        fact=dict(current_level=record["current_level"], suggestion=suggestion, model=ctx.model),
    )
    protected = lemma.difficulty_level in COHORT_LEVELS or (
        lemma.difficulty_level is not None and 1 <= lemma.difficulty_level <= 499
    )
    if protected or _current_fingerprint(session, lemma) != record["fingerprint"]:
        return Done("rejected", "Stale sense/evidence or protected placement; suggestion saved")
    if not state["apply_results"]:
        return Done("written", "Suggestion saved; application was not authorized")
    target = 1399 if suggestion["fit"] == "none" else suggestion["level"]
    if type(target) is not int or target not in record["allowed"]:
        raise ValueError("Destination is not allowed")
    if target != lemma.difficulty_level:
        _backup_once(session, state)
        apply_moves(
            session,
            [
                PlannedMove(
                    lemma.id,
                    record["guid"],
                    lemma.difficulty_level,
                    target,
                    suggestion["reasoning"],
                )
            ],
            source=source,
        )
    log_entity_operation(
        session,
        source=source,
        operation_type="curriculum_placement_applied",
        entity_guid=lemma.guid,
        lemma_id=lemma.id,
        fact=dict(
            original_fingerprint=record["fingerprint"],
            applied_fingerprint=_current_fingerprint(session, lemma),
            level=target,
            suggestion=suggestion,
        ),
    )
    return Done("written", f"Placement applied: {record['current_level']} -> {target}")


PLACEMENT_JOB = Job(
    name="curriculum_review",
    stages=(Stage("levels.placement", _prepare, _apply),),
    item_key=lambda state: str(state["record"]["guid"]),
)
