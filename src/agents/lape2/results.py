"""Validate each requested answer and stage additive, confidence-gated writes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from agents.lape2.planner import Question, RequestPlan, question_key, source_snapshot, stored_values
from langtools.inflection import inflect
from storage.crud.operation_log import log_entity_operation
from storage.crud.uncertain_llm_result import LLMQuestion, confidence_gated
from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Lemma


@dataclass(frozen=True)
class Answer:
    value: str
    confidence: float
    explanation: str


@dataclass
class ApplyReport:
    written: int = 0
    rejected: int = 0
    skipped: int = 0
    errors: dict[str, str] = field(default_factory=dict)


def validate_answer(question: Question, raw: Any) -> Answer:
    # Accept explanations from already submitted batches using the old schema.
    if not isinstance(raw, dict) or set(raw) not in (
        {"value", "confidence"},
        {"value", "confidence", "explanation"},
    ):
        raise ValueError("Answer must contain value and confidence, with an optional explanation")
    value, confidence, explanation = raw["value"], raw["confidence"], raw.get("explanation", "")
    if not isinstance(value, str) or not isinstance(explanation, str):
        raise ValueError("Value and explanation must be strings")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("Confidence must be a finite number from 0 to 1")
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise ValueError("Value must be a single canonical form, not multiple lines")
    if not value and question.kind != "override":
        raise ValueError("An explicit value is required")
    if question.values and value not in question.values:
        raise ValueError(f"Value must be one of {question.values}")
    return Answer(value, float(confidence), explanation.strip())


def _put_grammar(
    session: Session, lemma_id: int, language_code: str, fact_type: str, value: str, notes: str
) -> None:
    row = (
        session.query(GrammarFact)
        .filter_by(lemma_id=lemma_id, language_code=language_code, fact_type=fact_type)
        .one_or_none()
    )
    if row is None:
        row = GrammarFact(lemma_id=lemma_id, language_code=language_code, fact_type=fact_type)
        session.add(row)
    elif row.fact_value and row.fact_value.strip():
        if row.fact_value != value:
            raise ValueError(f"Existing {language_code} {fact_type} differs; review required")
        return
    row.fact_value, row.notes, row.verified = value, notes, False


@confidence_gated(
    question=lambda args: LLMQuestion(
        args["question"].completion_type, args["question"].language_code, lemma_id=args["lemma_id"]
    ),
    value="completion_value",
    notes_arg="notes",
)
def store_answer(
    session: Session,
    lemma_id: int,
    question: Question,
    completion_value: str,
    form_value: str,
    notes: str,
    *,
    confidence: float | None = None,
    min_confidence: float | None = None,
    model: str | None = None,
) -> bool | None:
    """Stage one answer, including an override/status pair, without committing."""
    if question.kind == "concept":
        row = (
            session.query(LemmaFact)
            .filter_by(lemma_id=lemma_id, fact_type=question.fact_type)
            .one_or_none()
        )
        if row is None:
            row = LemmaFact(lemma_id=lemma_id, fact_type=question.fact_type)
            session.add(row)
        elif row.fact_value and row.fact_value.strip():
            return False
        row.fact_value, row.notes, row.verified = completion_value, notes, False
    else:
        language_code = str(question.language_code)
        if question.kind == "override" and completion_value == "override":
            _put_grammar(session, lemma_id, language_code, question.fact_type, form_value, notes)
        _put_grammar(
            session, lemma_id, language_code, question.completion_type, completion_value, notes
        )
    return True


def _completion_value(
    question: Question, answer: Answer, source: dict[str, Any], known: dict[str, str]
) -> str:
    if question.kind != "override":
        return answer.value
    language_code = str(question.language_code)
    facts: dict[str, str | None] = {
        identifier.split("__", 1)[1]: value
        for identifier, value in known.items()
        if identifier.startswith(f"{language_code}__")
    }
    if question.fact_type == "plural":
        number_type = facts.get("number_type")
        if number_type is None:
            raise ValueError("A confident number_type is required before completing a plural check")
        absent = number_type in {"singulare_tantum", "uncountable"}
        if (
            number_type == "plurale_tantum"
            and answer.value != source["translations"][language_code]
        ):
            raise ValueError("Plural-only noun must keep the supplied plural text")
    elif question.fact_type in {"comparative", "superlative"} and language_code == "en":
        if "gradability" not in facts:
            raise ValueError(
                "A confident gradability is required before completing comparison checks"
            )
        absent = facts["gradability"] == "non_gradable"
    elif question.fact_type in {"comparative", "superlative"}:
        # These languages have no registered gradability classification yet;
        # the model's explicit empty-form decision is still confidence-gated.
        absent = not answer.value
    else:
        absent = False
    if absent:
        if answer.value:
            raise ValueError("Form contradicts the classification: this slot does not apply")
        return "not_applicable"
    if not answer.value:
        raise ValueError("This grammatical slot requires a form")
    # Exclude the target override so a stored answer cannot validate itself.
    facts.pop(question.fact_type, None)
    facts.pop(f"irregular_{question.fact_type}", None)
    forms = inflect(source["translations"][language_code], language_code, source["pos_type"], facts)
    slot = "singular_f" if question.fact_type == "feminine_form" else question.fact_type
    return "regular" if forms and forms.get(slot) == answer.value else "override"


def apply_answers(
    session: Session,
    plan: RequestPlan,
    data: dict[str, Any],
    *,
    min_confidence: float,
    model: str,
) -> ApplyReport:
    """Apply against the saved manifest, preserving edits made while it was out.

    The caller commits. Invalid/uncertain answers do not block unrelated facts.
    Source changes or edits to known context reject the whole stale response.
    """
    if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")
    lemma = session.get(Lemma, plan.lemma_id)
    if (
        lemma is None
        or source_snapshot(session, lemma, list(plan.source["translations"])) != plan.source
    ):
        raise ValueError("Stale request: lemma sense or translations changed")
    current = stored_values(session, plan.lemma_id)
    if any(current.get(identifier) != value for identifier, value in plan.known.items()):
        raise ValueError("Stale request: a previously known fact changed")
    report = ApplyReport()
    expected = {question.key for question in plan.questions}
    for unexpected in data.keys() - expected:
        report.errors[unexpected] = "Unrequested answer ignored"
        report.rejected += 1
    # Classifications/principal parts land first, independently of response order.
    ordered = sorted(plan.questions, key=lambda question: question.kind == "override")
    for question in ordered:
        completion_key = question_key(question.completion_type, question.language_code)
        existing_completion = current.get(completion_key)
        if existing_completion and (
            question.kind != "override"
            or existing_completion != "override"
            or question.key in current
        ):
            report.skipped += 1
            continue
        try:
            answer = validate_answer(question, data.get(question.key))
            if (
                question.kind == "override"
                and question.key in current
                and current[question.key] != answer.value
            ):
                raise ValueError("Existing override differs; review required")
            # Low-confidence form answers still get an uncertainty record when
            # their dependencies were uncertain too. No status is accepted.
            completion = (
                "unconfirmed"
                if question.kind == "override" and answer.confidence < min_confidence
                else _completion_value(question, answer, plan.source, current)
            )
            notes = f"Lape2 ({model}; confidence={answer.confidence:.3f})"
            if answer.explanation:
                notes += f": {answer.explanation}"
            if (
                existing_completion
                and answer.confidence >= min_confidence
                and existing_completion != completion
            ):
                raise ValueError("Existing completion status differs; review required")
        except ValueError as error:
            report.rejected += 1
            report.errors[question.key] = str(error)
            continue
        # Persistence/logging failures must reach the runner, which rolls the
        # lemma back. They are not malformed model answers to skip past.
        saved = store_answer(
            session,
            plan.lemma_id,
            question,
            completion,
            answer.value,
            notes,
            confidence=answer.confidence,
            min_confidence=min_confidence,
            model=model,
        )
        if saved:
            log_entity_operation(
                session,
                source="agents/lape2",
                operation_type="grammar_fact_generated",
                entity_guid=lemma.guid,
                lemma_id=lemma.id,
                fact={
                    "fact_type": question.fact_type,
                    "language_code": question.language_code,
                    "value": answer.value,
                    "completion": completion,
                    "model": model,
                    "confidence": answer.confidence,
                },
            )
            current[completion_key] = completion
            if question.kind == "override" and completion == "override":
                current[question.key] = answer.value
            report.written += 1
        else:
            report.rejected += 1
            report.errors[question.key] = "Below confidence threshold"
    return report
