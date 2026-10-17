"""One saved request manifest shared by inline and OpenAI batch execution."""

from typing import Any

from sqlalchemy.orm import Session

from agents.lape2.planner import RequestPlan, plan_request
from agents.lape2.query import build_query
from agents.lape2.results import apply_answers
from clients.types import LLMCall
from storage.models.schema import Lemma
from workqueue.llm_batch import Done, Job, Stage, StageContext


def prepare(session: Session, state: dict[str, Any], ctx: StageContext) -> LLMCall | Done:
    lemma = session.get(Lemma, state["lemma_id"])
    if lemma is None:
        return Done("failed", "Lemma no longer exists")
    plan = plan_request(
        session,
        lemma,
        state["languages"],
        facts=state.get("facts"),
        retry_uncertain=state.get("retry_uncertain", False),
    )
    if not plan.questions:
        return Done("skipped", "No actionable missing facts")
    state["plan"] = plan.to_dict()
    return build_query(plan)


def apply(session: Session, state: dict[str, Any], data: dict[str, Any], ctx: StageContext) -> Done:
    report = apply_answers(
        session,
        RequestPlan.from_dict(state["plan"]),
        data,
        min_confidence=state["min_confidence"],
        model=ctx.model,
    )
    detail = f"{report.written} written, {report.rejected} rejected, {report.skipped} preserved"
    if report.errors:
        detail += f"; {report.errors}"
    state["report"] = {
        "written": report.written,
        "rejected": report.rejected,
        "skipped": report.skipped,
        "errors": report.errors,
    }
    return Done(
        "written" if report.written else "rejected" if report.rejected else "skipped", detail
    )


def item_key(state: dict[str, Any]) -> str:
    # One in-flight request per lemma: overlapping language/fact filters must
    # not spend twice on the same questions.
    return str(state["lemma_id"])


LAPE2_JOB = Job("lape2", (Stage("lape2.grammar", prepare, apply),), item_key)
