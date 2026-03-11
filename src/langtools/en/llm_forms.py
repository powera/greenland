#!/usr/bin/python3

"""English language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.en.conjugation import expand_verb_forms
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm

logger = logging.getLogger(__name__)

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "verb")].form_mapping


def query_english_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate English verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        conjugation_forms = expand_verb_forms({"infinitive": lemma.lemma_text})
        projected_forms: Dict[str, str] = {}
        for form_name in VERB_FORM_MAPPING:
            if form_name in conjugation_forms:
                projected_forms[form_name] = conjugation_forms[form_name]

        if projected_forms:
            linguistic_db.log_query(
                session,
                word=lemma.lemma_text,
                query_type="english_verb_forms",
                prompt="[mechanical langtools.en.conjugation]",
                response=json.dumps(
                    {
                        "forms": projected_forms,
                        "notes": "mechanical expansion from infinitive",
                        "mechanical": True,
                    }
                ),
                model=client.default_model,
            )
            return projected_forms, True

        logger.info("Falling back to LLM for English verb '%s'", lemma.lemma_text)

    return query_forms(FORM_SPECS[("en", "verb")], client, lemma_id, get_session_func)


def query_english_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for English noun forms."""
    return query_forms(FORM_SPECS[("en", "noun")], client, lemma_id, get_session_func)


def query_english_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for English adjective forms."""
    return query_forms(FORM_SPECS[("en", "adjective")], client, lemma_id, get_session_func)


def query_english_adverb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for English adverb forms."""
    return query_forms(FORM_SPECS[("en", "adverb")], client, lemma_id, get_session_func)
