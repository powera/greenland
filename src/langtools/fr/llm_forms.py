#!/usr/bin/python3

"""French language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.fr.conjugation import conjugate
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

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
            conjugation, mechanical_success = conjugate(french_verb)
            if mechanical_success and conjugation.forms:
                linguistic_db.log_query(
                    session,
                    word=french_verb,
                    query_type="french_verb_conjugations",
                    prompt="[mechanical langtools.fr.conjugation]",
                    response=json.dumps(
                        {
                            "forms": conjugation.forms,
                            "confidence": conjugation.confidence,
                            "notes": conjugation.notes,
                            "mechanical": True,
                        }
                    ),
                    model=client.default_model,
                )
                return conjugation.forms, True
            logger.info("Falling back to LLM for French verb '%s'", french_verb)

    return query_forms(FORM_SPECS[("fr", "verb")], client, lemma_id, get_session_func)


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
