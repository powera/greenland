#!/usr/bin/python3

"""Spanish language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.es.conjugation import conjugate
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("es", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("es", "verb")].form_mapping


_DEF_PAST_SOURCE = "preterite"


def _project_spanish_forms_to_registry(forms: Dict[str, str]) -> Dict[str, str]:
    """Project rich Spanish conjugation output to registry-required fields."""
    projected_forms: Dict[str, str] = {}
    for form_name in VERB_FORM_MAPPING:
        person, tense = form_name.split("_", 1)
        if tense == "past":
            source_key = f"{person}_{_DEF_PAST_SOURCE}"
        else:
            source_key = f"{person}_{tense}"
        form_value = forms.get(source_key)
        if form_value:
            projected_forms[form_name] = form_value
    return projected_forms


def get_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Spanish noun forms."""
    return query_forms(FORM_SPECS[("es", "noun")], client, lemma_id, get_session_func)


def get_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Spanish verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        spanish_verb = get_translation(session, lemma, "es")
        if spanish_verb:
            conjugation_forms = conjugate(spanish_verb)
            if conjugation_forms:
                projected_forms = _project_spanish_forms_to_registry(conjugation_forms)
                if projected_forms:
                    linguistic_db.log_query(
                        session,
                        word=spanish_verb,
                        query_type="spanish_verb_conjugations",
                        prompt="[mechanical langtools.es.conjugation]",
                        response=json.dumps(
                            {
                                "forms": projected_forms,
                                "notes": "mechanical; past mapped from preterite",
                                "mechanical": True,
                            }
                        ),
                        model=client.default_model,
                    )
                    return projected_forms, True
            logger.info("Falling back to LLM for Spanish verb '%s'", spanish_verb)

    return query_forms(FORM_SPECS[("es", "verb")], client, lemma_id, get_session_func)


def query_spanish_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Backward-compatible alias for noun form generation."""
    return get_noun_forms(client, lemma_id, get_session_func)


def query_spanish_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Backward-compatible alias for verb form generation."""
    return get_verb_forms(client, lemma_id, get_session_func)
