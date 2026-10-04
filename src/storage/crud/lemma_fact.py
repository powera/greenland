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
    if fact_type == "has_individual_instances":
        legacy = (
            session.query(LemmaFact)
            .filter(LemmaFact.lemma_id == lemma_id, LemmaFact.fact_type == "quantifiable")
            .first()
        )
        if legacy is not None:
            session.delete(legacy)
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
    if fact is not None:
        return fact.fact_value
    if fact_type == "has_individual_instances":
        legacy = (
            session.query(LemmaFact)
            .filter(LemmaFact.lemma_id == lemma_id, LemmaFact.fact_type == "quantifiable")
            .first()
        )
        return legacy.fact_value if legacy else None
    return None


def get_lemma_facts_dict(session: Session, lemma_id: int) -> Dict[str, Optional[str]]:
    facts = {fact.fact_type: fact.fact_value for fact in get_lemma_facts(session, lemma_id)}
    if "quantifiable" in facts:
        facts.setdefault("has_individual_instances", facts["quantifiable"])
        del facts["quantifiable"]
    return facts


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


def get_has_individual_instances(session: Session, lemma_id: int) -> Optional[bool]:
    """True/False if classified, None if unclassified."""
    value = get_lemma_fact_value(session, lemma_id, "has_individual_instances")
    if value is None:
        return None
    return value == "true"


def get_quantifiable(session: Session, lemma_id: int) -> Optional[bool]:
    """Legacy name for :func:`get_has_individual_instances`."""
    return get_has_individual_instances(session, lemma_id)
