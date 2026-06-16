"""Look up Lithuanian verb principal parts from the database.

Principal parts are stored as GrammarFact rows and loaded via the standard
release file pipeline (sync_release.py import, migrate.py export).
"""

import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from storage.crud.grammar_fact import get_grammar_fact_value
from storage.crud.lemma import get_lemma_by_guid
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)


def get_principal_parts(session: Session, guid: str) -> Optional[Tuple[str, str, str]]:
    """Look up (infinitive, 3s_present, 3s_past) for a verb by GUID.

    Returns None if no principal parts are available for this GUID.
    """
    lemma = get_lemma_by_guid(session, guid)
    if not lemma:
        return None
    infinitive = get_grammar_fact_value(session, lemma.id, "lt", "infinitive")
    if not infinitive:
        infinitive = get_translation(session, lemma, "lt")
    present = get_grammar_fact_value(session, lemma.id, "lt", "3s_present")
    if not present:
        present = get_grammar_fact_value(session, lemma.id, "lt", "3p_present")
    past = get_grammar_fact_value(session, lemma.id, "lt", "3s_past")
    if not past:
        past = get_grammar_fact_value(session, lemma.id, "lt", "3p_past")
    if infinitive and present and past:
        return (infinitive, present, past)
    return None
