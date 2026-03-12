"""Look up Lithuanian verb principal parts (3p_present, 3p_past) from the database.

Principal parts are stored as GrammarFact rows and loaded via the standard
release file pipeline (sync_release.py import, migrate.py export).
"""

import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from storage.crud.grammar_fact import get_grammar_fact_value
from storage.crud.lemma import get_lemma_by_guid

logger = logging.getLogger(__name__)


def get_principal_parts(session: Session, guid: str) -> Optional[Tuple[str, str]]:
    """Look up (3p_present, 3p_past) for a verb by GUID.

    Returns None if no principal parts are available for this GUID.
    """
    lemma = get_lemma_by_guid(session, guid)
    if not lemma:
        return None
    present = get_grammar_fact_value(session, lemma.id, "lt", "3p_present")
    past = get_grammar_fact_value(session, lemma.id, "lt", "3p_past")
    if present and past:
        return (present, past)
    return None
