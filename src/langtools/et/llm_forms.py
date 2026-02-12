#!/usr/bin/python3

"""Estonian language form generation."""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("et", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("et", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("et", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("et", "verb")].form_mapping


def query_estonian_noun_declensions(
    client: UnifiedLLMClient,
    lemma_id: int,
    get_session_func: Callable[[], Session],
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Estonian noun forms."""
    return query_forms(FORM_SPECS[("et", "noun")], client, lemma_id, get_session_func)


def query_estonian_verb_conjugations(
    client: UnifiedLLMClient,
    lemma_id: int,
    get_session_func: Callable[[], Session],
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Estonian verb forms."""
    return query_forms(FORM_SPECS[("et", "verb")], client, lemma_id, get_session_func)


def query_estonian_adjective_declensions(
    client: UnifiedLLMClient,
    lemma_id: int,
    get_session_func: Callable[[], Session],
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Estonian adjective forms."""
    return query_forms(FORM_SPECS[("et", "adjective")], client, lemma_id, get_session_func)


def query_estonian_adverb_forms(
    client: UnifiedLLMClient,
    lemma_id: int,
    get_session_func: Callable[[], Session],
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Estonian adverb forms."""
    return query_forms(FORM_SPECS[("et", "adverb")], client, lemma_id, get_session_func)
