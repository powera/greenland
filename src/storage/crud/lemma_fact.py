"""CRUD operations for LemmaFact model (language-independent lemma facts)."""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from storage.config.lemma_fact_registry import LEMMA_FACT_DEFINITIONS, validate_lemma_fact
from storage.crud.uncertain_llm_result import LLMQuestion, confidence_gated
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


@confidence_gated(
    question=lambda a: LLMQuestion(a["fact_type"], None, lemma_id=a["lemma_id"]),
    value="fact_value",
    notes_arg="notes",
)
def add_lemma_fact(
    session: Session,
    lemma_id: int,
    fact_type: str,
    fact_value: str,
    notes: Optional[str] = None,
    verified: bool = False,
    *,
    confidence: Optional[float] = None,
    min_confidence: Optional[float] = None,
    model: Optional[str] = None,
) -> Optional[LemmaFact]:
    """Set a lemma fact, replacing any existing value of the same type.

    ``confidence``, ``min_confidence`` and ``model`` are for an LLM's answer;
    see storage.crud.uncertain_llm_result.confidence_gated.  An answer below
    min_confidence is recorded as uncertain, not set.

    Returns None (and writes nothing) if the type or value fails registry
    validation, or the answer was not confident enough.
    """
    error = validate_lemma_fact(fact_type, fact_value)
    if error is not None:
        logger.warning(f"Rejected lemma fact for lemma_id={lemma_id}: {error}")
        return None

    lemma = session.get(Lemma, lemma_id)
    if lemma is None or lemma.pos_type not in LEMMA_FACT_DEFINITIONS[fact_type].required_pos:
        logger.warning("Rejected %s for incompatible or missing lemma %s", fact_type, lemma_id)
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
    if fact is not None:
        return fact.fact_value
    return None


def get_lemma_facts_dict(session: Session, lemma_id: int) -> Dict[str, Optional[str]]:
    facts = {fact.fact_type: fact.fact_value for fact in get_lemma_facts(session, lemma_id)}
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


def get_individuation(session: Session, lemma_id: int) -> Optional[str]:
    """The concept's organization, or None when unclassified."""
    return get_lemma_fact_value(session, lemma_id, "individuation")


def get_concreteness(session: Session, lemma_id: int) -> Optional[str]:
    """The concept's physical/abstract classification, or None when unclassified."""
    return get_lemma_fact_value(session, lemma_id, "concreteness")
