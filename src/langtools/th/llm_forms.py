#!/usr/bin/python3

"""Thai language form generation."""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("th", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("th", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("th", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("th", "verb")].form_mapping


def query_thai_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Thai noun forms."""
    return query_forms(FORM_SPECS[("th", "noun")], client, lemma_id, get_session_func)


def query_thai_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Thai verb forms."""
    return query_forms(FORM_SPECS[("th", "verb")], client, lemma_id, get_session_func)


def query_thai_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Thai adjective forms."""
    return query_forms(FORM_SPECS[("th", "adjective")], client, lemma_id, get_session_func)


def query_thai_adverb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Thai adverb forms."""
    return query_forms(FORM_SPECS[("th", "adverb")], client, lemma_id, get_session_func)
