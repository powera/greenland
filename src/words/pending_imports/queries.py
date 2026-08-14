"""Read-only views of the pending-import queue.

Used by the Dramblys CLI and anything else that wants to see what is waiting
without touching it. Nothing here writes or commits.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from storage.models.imports import (
    PendingImport,
    PendingImportSynonymCandidate,
    SentencePendingImport,
)
from util.logging_config import get_logger
from words.pending_imports.synonym_screening import ACTIVE_STATUS

logger = get_logger(__name__)


def _synonym_candidate_counts(session: Session, pending_import_id: int) -> tuple[int, int]:
    """Active and strong-active synonym candidate counts for one row."""
    active = (
        session.query(PendingImportSynonymCandidate)
        .filter(
            PendingImportSynonymCandidate.pending_import_id == pending_import_id,
            PendingImportSynonymCandidate.status == ACTIVE_STATUS,
        )
        .count()
    )
    strong = (
        session.query(PendingImportSynonymCandidate)
        .filter(
            PendingImportSynonymCandidate.pending_import_id == pending_import_id,
            PendingImportSynonymCandidate.status == ACTIVE_STATUS,
            PendingImportSynonymCandidate.is_strong.is_(True),
        )
        .count()
    )
    return int(active), int(strong)


def list_pending_imports(
    session: Any,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    limit: Optional[int] = None,
    target_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List words in the pending_imports staging table.

    Args:
        session: Database session
        pos_type: Filter by POS type (noun, verb, adjective, adverb)
        pos_subtype: Filter by POS subtype
        limit: Maximum number of results to return
        target_kind: Filter by what the term will become (lemma, name, concept)

    Returns:
        Dictionary with pending imports
    """
    logger.info("Listing pending imports...")

    try:
        query = session.query(PendingImport)

        if pos_type:
            query = query.filter(PendingImport.pos_type == pos_type)
        if pos_subtype:
            query = query.filter(PendingImport.pos_subtype == pos_subtype)
        if target_kind:
            query = query.filter(PendingImport.target_kind == target_kind)

        query = query.order_by(PendingImport.frequency_rank.nullslast(), PendingImport.added_at)

        if limit:
            query = query.limit(limit)

        pending_imports = query.all()

        results: List[Dict[str, Any]] = []
        for pending in pending_imports:
            synonym_candidate_count, strong_synonym_candidate_count = _synonym_candidate_counts(
                session, pending.id
            )
            waiting_sentence_count = int(
                session.query(SentencePendingImport)
                .filter(SentencePendingImport.pending_import_id == pending.id)
                .count()
            )
            results.append(
                {
                    "id": pending.id,
                    "english_word": pending.english_word,
                    "definition": pending.definition,
                    "translation": pending.disambiguation_translation,
                    "language": pending.disambiguation_language,
                    "target_kind": pending.target_kind,
                    "name_kind": pending.name_kind,
                    "concept_type": pending.concept_type,
                    "pos_type": pending.pos_type,
                    "pos_subtype": pending.pos_subtype,
                    "source": pending.source,
                    "frequency_rank": pending.frequency_rank,
                    "notes": pending.notes,
                    "synonym_candidate_count": synonym_candidate_count,
                    "strong_synonym_candidate_count": strong_synonym_candidate_count,
                    "waiting_sentence_count": waiting_sentence_count,
                    "added_at": pending.added_at.isoformat() if pending.added_at else None,
                }
            )

        logger.info(f"Found {len(results)} pending imports")

        return {"count": len(results), "pending_imports": results}

    except Exception as e:
        logger.error(f"Error listing pending imports: {e}")
        return {"error": str(e), "count": 0, "pending_imports": []}
