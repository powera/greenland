"""One saved request manifest shared by inline and OpenAI batch execution."""

from typing import Any

from sqlalchemy.orm import Session

from agents.lape2.planner import RequestPlan, plan_request
from agents.lape2.query import build_query
from agents.lape2.results import apply_answers
from clients.types import LLMCall
from storage.models.schema import Lemma
from words.mechanical_forms import generate_lemma_forms
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
    plan = RequestPlan.from_dict(state["plan"])
    report = apply_answers(
        session,
        plan,
        data,
        min_confidence=state["min_confidence"],
        model=ctx.model,
    )
    forms_added = 0
    lemma = session.get(Lemma, state["lemma_id"])
    if report.written and lemma is not None:
        session.flush()
        blocked_questions = set(report.errors) | set(plan.uncertain)
        for language in state["languages"]:
            # Do not derive a paradigm using assumed defaults after rejecting
            # an uncertain classification in this language.
            if any(identifier.startswith(f"{language}__") for identifier in blocked_questions):
                continue
            forms_added += generate_lemma_forms(session, lemma, language)["forms_added"]
    detail = f"{report.written} written, {report.rejected} rejected, {report.skipped} preserved"
    detail += f"; {forms_added} mechanical forms added"
    if report.errors:
        detail += f"; {report.errors}"
    state["report"] = {
        "written": report.written,
        "rejected": report.rejected,
        "skipped": report.skipped,
        "errors": report.errors,
        "forms_added": forms_added,
    }
    return Done(
        "written" if report.written else "rejected" if report.rejected else "skipped", detail
    )


def item_key(state: dict[str, Any]) -> str:
    # One in-flight request per lemma: overlapping language/fact filters must
    # not spend twice on the same questions.
    return str(state["lemma_id"])


LAPE2_JOB = Job("lape2", (Stage("lape2.grammar", prepare, apply),), item_key)
