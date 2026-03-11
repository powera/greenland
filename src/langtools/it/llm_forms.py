#!/usr/bin/python3

"""Italian language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.it.conjugation import conjugate
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("it", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("it", "verb")].form_mapping


def query_italian_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Italian noun forms."""
    return query_forms(FORM_SPECS[("it", "noun")], client, lemma_id, get_session_func)


def query_italian_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Italian verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        italian_verb = get_translation(session, lemma, "it")
        if italian_verb:
            conjugation_forms = conjugate(italian_verb)
            if conjugation_forms:
                linguistic_db.log_query(
                    session,
                    word=italian_verb,
                    query_type="italian_verb_forms",
                    prompt="[mechanical langtools.it.conjugation]",
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
            logger.info("Falling back to LLM for Italian verb '%s'", italian_verb)

    return query_forms(FORM_SPECS[("it", "verb")], client, lemma_id, get_session_func)
