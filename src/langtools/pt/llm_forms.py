#!/usr/bin/python3

"""Portuguese language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from langtools.pt.conjugation import conjugate
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pt", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pt", "verb")].form_mapping


def query_portuguese_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Portuguese noun forms."""
    return query_forms(FORM_SPECS[("pt", "noun")], client, lemma_id, get_session_func)


def query_portuguese_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Portuguese verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        portuguese_verb = get_translation(session, lemma, "pt")
        if portuguese_verb:
            conjugation_forms = conjugate(portuguese_verb)
            if conjugation_forms:
                linguistic_db.log_query(
                    session,
                    word=portuguese_verb,
                    query_type="portuguese_verb_forms",
                    prompt="[mechanical langtools.pt.conjugation]",
                    response=json.dumps(
                        {
                            "forms": conjugation_forms,
                            "notes": "mechanical regular conjugation",
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return conjugation_forms, True
            logger.info("Falling back to LLM for Portuguese verb '%s'", portuguese_verb)

    return query_forms(FORM_SPECS[("pt", "verb")], client, lemma_id, get_session_func)
