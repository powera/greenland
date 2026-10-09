"""CRUD operations for UncertainLLMResult (questions an LLM was unsure of).

Each function takes exactly one of ``lemma_id`` / ``sentence_id``.  None of
them commits; the caller does, so a fact and the clearing of its uncertainty
land together.

Most code should not call these directly.  Put :func:`confidence_gated` on
the writer that stores an LLM's answer, and pass the model's confidence to
it; the decorator stores a confident answer, records an uncertain one here,
and clears the record whenever the writer stores a value.
"""

import functools
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Optional, ParamSpec, TypeVar, Union

from sqlalchemy.orm import Query, Session

from storage.models.uncertain_llm_result import REASON_LOW_CONFIDENCE, UncertainLLMResult

P = ParamSpec("P")
R = TypeVar("R")

# Keyword-only parameters a gated writer declares; the decorator consumes them.
GATE_PARAMS = ("confidence", "min_confidence", "model")

DEFAULT_MIN_CONFIDENCE = 0.7

# Every gated writer, by name, so a test can check that LLM code passes a
# confidence to each of them.
GATED_WRITERS: Dict[str, "ConfidenceGated[Any, Any]"] = {}


@dataclass(frozen=True)
class LLMQuestion:
    """What was asked, about what: the key of one uncertain_llm_results row."""

    topic: str
    language_code: Optional[str] = None
    lemma_id: Optional[int] = None
    sentence_id: Optional[int] = None


ArgReader = Callable[[Dict[str, Any]], Any]


class ConfidenceGated(Generic[P, R]):
    """A writer that, given ``confidence=``, writes only a confident answer.

    See :func:`confidence_gated`.
    """

    def __init__(
        self,
        writer: Callable[P, R],
        question: Callable[[Dict[str, Any]], LLMQuestion],
        value: Union[str, ArgReader],
        notes_arg: Optional[str],
        min_confidence: float,
    ) -> None:
        self._writer = writer
        self._question = question
        self._value = value
        self._notes_arg = notes_arg
        self._min_confidence = min_confidence
        self._signature = inspect.signature(writer)
        parameters = self._signature.parameters
        if "session" not in parameters:
            raise TypeError(f"{writer.__name__} needs a 'session' parameter to be gated")
        for name in GATE_PARAMS:
            parameter = parameters.get(name)
            if parameter is None or parameter.kind is not inspect.Parameter.KEYWORD_ONLY:
                raise TypeError(f"{writer.__name__} must declare keyword-only '{name}' to be gated")
        functools.update_wrapper(self, writer)
        GATED_WRITERS[writer.__name__] = self

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        bound = self._signature.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = bound.arguments
        confidence = arguments["confidence"]
        session: Session = arguments["session"]
        question = self._question(arguments)
        if confidence is not None:
            value = (
                arguments[self._value] if isinstance(self._value, str) else self._value(arguments)
            )
            if not value:
                # No answer -- also how a failed call looks, so nothing is recorded.
                return None  # type: ignore[return-value]
            min_confidence = arguments["min_confidence"]
            if min_confidence is None:
                min_confidence = self._min_confidence
            if confidence < min_confidence:
                notes = arguments[self._notes_arg] if self._notes_arg else None
                record_uncertain_llm_result(
                    session,
                    question.topic,
                    question.language_code,
                    REASON_LOW_CONFIDENCE,
                    note=_uncertain_note(arguments["model"], value, confidence, notes),
                    lemma_id=question.lemma_id,
                    sentence_id=question.sentence_id,
                )
                return None  # type: ignore[return-value]
        # Cleared before the write so it lands in the writer's own transaction:
        # a writer that commits commits it, one that rolls back restores it.
        clear_uncertain_llm_result(
            session,
            question.topic,
            question.language_code,
            lemma_id=question.lemma_id,
            sentence_id=question.sentence_id,
        )
        return self._writer(*args, **kwargs)

    def is_uncertain(self, session: Session, **key_args: Any) -> bool:
        """Whether a model was uncertain of the question these arguments name.

        Pass the writer's arguments that the question is built from, by name,
        e.g. ``add_grammar_fact.is_uncertain(session, lemma_id=1,
        language_code="es", fact_type="grammatical_gender")``.
        """
        question = self._question(key_args)
        return (
            get_uncertain_llm_result(
                session,
                question.topic,
                question.language_code,
                lemma_id=question.lemma_id,
                sentence_id=question.sentence_id,
            )
            is not None
        )


def confidence_gated(
    question: Callable[[Dict[str, Any]], LLMQuestion],
    value: Union[str, ArgReader],
    notes_arg: Optional[str] = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Callable[[Callable[P, R]], ConfidenceGated[P, R]]:
    """Gate a writer of LLM answers on the model's confidence.

    The writer declares keyword-only ``confidence``, ``min_confidence`` and
    ``model`` (all defaulting to None) and otherwise ignores them.  Called
    without ``confidence`` it is the plain writer: hand edits and imports
    are unaffected.  Called with it:

    * no value -> writes nothing and records nothing; returns None.
    * below ``min_confidence`` (the call's, else the decorator's) -> records
      the question in uncertain_llm_results; returns None.
    * otherwise -> the plain write.

    Every write, gated or not, clears the question's uncertain row.

    Args:
        question: Builds the question's key from the writer's arguments, by
            name.  Also used by ``is_uncertain``, so it must read only the
            arguments that name the question.
        value: The argument holding the answer, or a function of the
            arguments for an answer spread over several (a pair of forms).
        notes_arg: The argument holding the model's explanation, copied
            into the uncertain row's note.
        min_confidence: The floor when a call passes none.
    """

    def decorate(writer: Callable[P, R]) -> ConfidenceGated[P, R]:
        return ConfidenceGated(writer, question, value, notes_arg, min_confidence)

    return decorate


def _uncertain_note(
    model: Optional[str], value: Any, confidence: float, notes: Optional[str]
) -> str:
    """``"gpt-6-luna leaned masculine (0.55): <the model's notes>"``."""
    note = f"{model or 'unknown model'} leaned {value} ({confidence:.2f})"
    return f"{note}: {notes}" if notes else note


def _query(
    session: Session,
    topic: str,
    language_code: Optional[str],
    lemma_id: Optional[int],
    sentence_id: Optional[int],
) -> "Query[UncertainLLMResult]":
    if (lemma_id is None) == (sentence_id is None):
        raise ValueError("Pass exactly one of lemma_id or sentence_id")
    query = session.query(UncertainLLMResult).filter(UncertainLLMResult.topic == topic)
    if lemma_id is not None:
        query = query.filter(UncertainLLMResult.lemma_id == lemma_id)
    else:
        query = query.filter(UncertainLLMResult.sentence_id == sentence_id)
    if language_code is None:
        return query.filter(UncertainLLMResult.language_code.is_(None))
    return query.filter(UncertainLLMResult.language_code == language_code)


def get_uncertain_llm_result(
    session: Session,
    topic: str,
    language_code: Optional[str],
    *,
    lemma_id: Optional[int] = None,
    sentence_id: Optional[int] = None,
) -> Optional[UncertainLLMResult]:
    """The row for this question, or None."""
    result: Optional[UncertainLLMResult] = _query(
        session, topic, language_code, lemma_id, sentence_id
    ).first()
    return result


def record_uncertain_llm_result(
    session: Session,
    topic: str,
    language_code: Optional[str],
    reason: str,
    note: Optional[str] = None,
    *,
    lemma_id: Optional[int] = None,
    sentence_id: Optional[int] = None,
) -> UncertainLLMResult:
    """Record that an LLM was uncertain of this question, replacing any earlier row."""
    row = get_uncertain_llm_result(
        session, topic, language_code, lemma_id=lemma_id, sentence_id=sentence_id
    )
    if row is None:
        row = UncertainLLMResult(
            lemma_id=lemma_id,
            sentence_id=sentence_id,
            language_code=language_code,
            topic=topic,
        )
        session.add(row)
    row.reason = reason
    row.note = note
    session.flush()
    return row


def clear_uncertain_llm_result(
    session: Session,
    topic: str,
    language_code: Optional[str],
    *,
    lemma_id: Optional[int] = None,
    sentence_id: Optional[int] = None,
) -> bool:
    """Delete the row for this question; return whether there was one."""
    deleted = _query(session, topic, language_code, lemma_id, sentence_id).delete(
        synchronize_session="fetch"
    )
    return bool(deleted)
