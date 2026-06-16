#!/usr/bin/python3

"""Italian language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.it.conjugation import conjugate
from langtools.it.derivative_forms import derive_adjective_forms, derive_noun_forms
from langtools.llm_forms_base import query_forms
from langtools.verb_overrides import (
    apply_verb_form_overrides,
    get_complete_verb_form_overrides,
)
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.crud.grammar_fact import get_grammar_fact_value, get_verb_form_overrides
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("it", "adjective")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("it", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("it", "verb")].form_mapping


def query_italian_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Italian noun forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "noun":
        italian_noun = get_translation(session, lemma, "it")
        if italian_noun:
            plural_form = get_grammar_fact_value(session, lemma.id, "it", "plural")
            noun_forms = derive_noun_forms(italian_noun, explicit_plural=plural_form)
            if noun_forms:
                linguistic_db.log_query(
                    session,
                    word=italian_noun,
                    query_type="italian_noun_forms",
                    prompt="[mechanical langtools.it.derivative_forms]",
                    response=json.dumps(
                        {
                            "forms": noun_forms,
                            "notes": "mechanical regular noun derivation",
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return noun_forms, True
            logger.info("Falling back to LLM for Italian noun '%s'", italian_noun)

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
            present_1s = get_grammar_fact_value(session, lemma.id, "it", "1s_present")
            past_1s = get_grammar_fact_value(session, lemma.id, "it", "1s_past")
            future_1s = get_grammar_fact_value(session, lemma.id, "it", "1s_future")
            conjugation_forms = conjugate(
                italian_verb,
                present_1s=present_1s,
                past_1s=past_1s,
                future_1s=future_1s,
            )
            if conjugation_forms:
                conjugation_forms = apply_verb_form_overrides(
                    conjugation_forms,
                    get_verb_form_overrides(session, lemma.id, "it"),
                )
                assert conjugation_forms is not None
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
            override_forms = get_complete_verb_form_overrides(session, lemma.id, "it")
            if override_forms:
                linguistic_db.log_query(
                    session,
                    word=italian_verb,
                    query_type="italian_verb_forms",
                    prompt="[grammar fact verb_form_* overrides]",
                    response=json.dumps(
                        {
                            "forms": override_forms,
                            "notes": "exact forms from grammar facts",
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return override_forms, True
            logger.info("Falling back to LLM for Italian verb '%s'", italian_verb)

    return query_forms(FORM_SPECS[("it", "verb")], client, lemma_id, get_session_func)


def query_italian_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Italian adjective agreement forms mechanically when possible."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "adjective":
        italian_adjective = get_translation(session, lemma, "it")
        if italian_adjective:
            adjective_forms = derive_adjective_forms(italian_adjective)
            if adjective_forms:
                linguistic_db.log_query(
                    session,
                    word=italian_adjective,
                    query_type="italian_adjective_forms",
                    prompt="[mechanical langtools.it.derivative_forms]",
                    response=json.dumps(
                        {
                            "forms": adjective_forms,
                            "notes": "mechanical adjective agreement derivation",
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return adjective_forms, True
            logger.info("Falling back to LLM for Italian adjective '%s'", italian_adjective)

    return query_forms(FORM_SPECS[("it", "adjective")], client, lemma_id, get_session_func)
