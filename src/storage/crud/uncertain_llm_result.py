"""CRUD operations for UncertainLLMResult (questions an LLM was unsure of).

Each function takes exactly one of ``lemma_id`` / ``sentence_id``.  None of
them commits; the caller does, so a fact and the clearing of its uncertainty
land together.
"""

from typing import Optional

from sqlalchemy.orm import Query, Session

from storage.models.uncertain_llm_result import UncertainLLMResult


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
