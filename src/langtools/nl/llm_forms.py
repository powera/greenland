#!/usr/bin/python3

"""Dutch language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from langtools.nl.conjugation import conjugate
from langtools.verb_overrides import (
    apply_verb_form_overrides,
    get_complete_verb_form_overrides,
)
from sqlalchemy.orm import Session
from storage.crud.grammar_fact import get_verb_form_overrides
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("nl", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("nl", "verb")].form_mapping


def query_dutch_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Dutch noun forms."""
    return query_forms(FORM_SPECS[("nl", "noun")], client, lemma_id, get_session_func)


def query_dutch_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Dutch verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        dutch_verb = get_translation(session, lemma, "nl")
        if dutch_verb:
            conjugation_forms = conjugate(dutch_verb)
            if conjugation_forms:
                conjugation_forms = apply_verb_form_overrides(
                    conjugation_forms,
                    get_verb_form_overrides(session, lemma.id, "nl"),
                )
                assert conjugation_forms is not None
                linguistic_db.log_query(
                    session,
                    word=dutch_verb,
                    query_type="dutch_verb_forms",
                    prompt="[mechanical langtools.nl.conjugation]",
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
            override_forms = get_complete_verb_form_overrides(session, lemma.id, "nl")
            if override_forms:
                linguistic_db.log_query(
                    session,
                    word=dutch_verb,
                    query_type="dutch_verb_forms",
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
            logger.info("Falling back to LLM for Dutch verb '%s'", dutch_verb)

    return query_forms(FORM_SPECS[("nl", "verb")], client, lemma_id, get_session_func)
