"""CRUD operations for LemmaFact model (language-independent lemma facts)."""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from storage.config.lemma_fact_registry import validate_lemma_fact
from storage.models.lemma_fact import LemmaFact

logger = logging.getLogger(__name__)


def add_lemma_fact(
    session: Session,
    lemma_id: int,
    fact_type: str,
    fact_value: str,
    notes: Optional[str] = None,
    verified: bool = False,
) -> Optional[LemmaFact]:
    """Set a lemma fact, replacing any existing value of the same type.

    Returns None (and writes nothing) if the type or value fails registry
    validation.
    """
    error = validate_lemma_fact(fact_type, fact_value)
    if error is not None:
        logger.warning(f"Rejected lemma fact for lemma_id={lemma_id}: {error}")
        return None

    fact = (
        session.query(LemmaFact)
        .filter(LemmaFact.lemma_id == lemma_id, LemmaFact.fact_type == fact_type)
        .first()
    )
    if fact is None:
        fact = LemmaFact(lemma_id=lemma_id, fact_type=fact_type)
        session.add(fact)
    fact.fact_value = fact_value
    fact.notes = notes
    fact.verified = verified
    session.commit()
    return fact


def get_lemma_facts(
    session: Session, lemma_id: int, fact_type: Optional[str] = None
) -> List[LemmaFact]:
    query = session.query(LemmaFact).filter(LemmaFact.lemma_id == lemma_id)
    if fact_type:
        query = query.filter(LemmaFact.fact_type == fact_type)
    result: List[LemmaFact] = query.order_by(LemmaFact.fact_type).all()
    return result


def get_lemma_fact_value(session: Session, lemma_id: int, fact_type: str) -> Optional[str]:
    fact = (
        session.query(LemmaFact)
        .filter(LemmaFact.lemma_id == lemma_id, LemmaFact.fact_type == fact_type)
        .first()
    )
    return fact.fact_value if fact else None


def get_lemma_facts_dict(session: Session, lemma_id: int) -> Dict[str, Optional[str]]:
    return {fact.fact_type: fact.fact_value for fact in get_lemma_facts(session, lemma_id)}


def delete_lemma_fact(session: Session, lemma_id: int, fact_type: str) -> bool:
    fact = (
        session.query(LemmaFact)
        .filter(LemmaFact.lemma_id == lemma_id, LemmaFact.fact_type == fact_type)
        .first()
    )
    if fact is None:
        return False
    session.delete(fact)
    session.commit()
    return True


def get_quantifiable(session: Session, lemma_id: int) -> Optional[bool]:
    """True/False if classified, None if unclassified."""
    value = get_lemma_fact_value(session, lemma_id, "quantifiable")
    if value is None:
        return None
    return value == "true"
