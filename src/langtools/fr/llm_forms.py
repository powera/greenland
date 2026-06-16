#!/usr/bin/python3

"""French language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.fr.conjugation import conjugate
from langtools.fr.inflection import build_adjective_forms
from langtools.llm_forms_base import query_forms
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

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("fr", "adjective")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("fr", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("fr", "verb")].form_mapping


def get_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for French noun forms."""
    return query_forms(FORM_SPECS[("fr", "noun")], client, lemma_id, get_session_func)


def get_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate French verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        french_verb = get_translation(session, lemma, "fr")
        if french_verb:
            conjugation_forms = conjugate(french_verb)
            if conjugation_forms:
                conjugation_forms = apply_verb_form_overrides(
                    conjugation_forms,
                    get_verb_form_overrides(session, lemma.id, "fr"),
                )
                assert conjugation_forms is not None
                linguistic_db.log_query(
                    session,
                    word=french_verb,
                    query_type="french_verb_conjugations",
                    prompt="[mechanical langtools.fr.conjugation]",
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
            override_forms = get_complete_verb_form_overrides(session, lemma.id, "fr")
            if override_forms:
                linguistic_db.log_query(
                    session,
                    word=french_verb,
                    query_type="french_verb_conjugations",
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
            logger.info("Falling back to LLM for French verb '%s'", french_verb)

    return query_forms(FORM_SPECS[("fr", "verb")], client, lemma_id, get_session_func)


def get_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate French adjective forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "adjective":
        french_adjective = get_translation(session, lemma, "fr")
        if french_adjective:
            adjective_forms = build_adjective_forms(french_adjective)
            if adjective_forms:
                linguistic_db.log_query(
                    session,
                    word=french_adjective,
                    query_type="french_adjective_forms",
                    prompt="[mechanical langtools.fr.inflection]",
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
            logger.info("Falling back to LLM for French adjective '%s'", french_adjective)

    return query_forms(FORM_SPECS[("fr", "adjective")], client, lemma_id, get_session_func)


def query_french_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Backward-compatible alias for noun form generation."""
    return get_noun_forms(client, lemma_id, get_session_func)


def query_french_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Backward-compatible alias for verb form generation."""
    return get_verb_forms(client, lemma_id, get_session_func)


def query_french_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Backward-compatible alias for adjective form generation."""
    return get_adjective_forms(client, lemma_id, get_session_func)
