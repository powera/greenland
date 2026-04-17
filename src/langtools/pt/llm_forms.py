#!/usr/bin/python3

"""Portuguese language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from langtools.pt.conjugation import conjugate
from langtools.pt.inflection import build_adjective_forms, build_noun_forms
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pt", "adjective")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pt", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pt", "verb")].form_mapping


def query_portuguese_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Portuguese noun forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "noun":
        portuguese_noun = get_translation(session, lemma, "pt")
        if portuguese_noun:
            noun_forms = build_noun_forms(portuguese_noun)
            if noun_forms:
                linguistic_db.log_query(
                    session,
                    word=portuguese_noun,
                    query_type="portuguese_noun_forms",
                    prompt="[mechanical langtools.pt.inflection]",
                    response=json.dumps(
                        {
                            "forms": noun_forms,
                            "notes": "mechanical singular/plural generation",
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return noun_forms, True
            logger.info("Falling back to LLM for Portuguese noun '%s'", portuguese_noun)

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


def query_portuguese_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Portuguese adjective forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "adjective":
        portuguese_adjective = get_translation(session, lemma, "pt")
        if portuguese_adjective:
            adjective_forms = build_adjective_forms(portuguese_adjective)
            if adjective_forms:
                linguistic_db.log_query(
                    session,
                    word=portuguese_adjective,
                    query_type="portuguese_adjective_forms",
                    prompt="[mechanical langtools.pt.inflection]",
                    response=json.dumps(
                        {
                            "forms": adjective_forms,
                            "notes": "mechanical adjective agreement generation",
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return adjective_forms, True
            logger.info("Falling back to LLM for Portuguese adjective '%s'", portuguese_adjective)

    return query_forms(FORM_SPECS[("pt", "adjective")], client, lemma_id, get_session_func)
