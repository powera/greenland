#!/usr/bin/python3

"""Ukrainian language form generation."""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("uk", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("uk", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("uk", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("uk", "verb")].form_mapping


def query_ukrainian_noun_declensions(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Ukrainian noun forms."""
    return query_forms(FORM_SPECS[("uk", "noun")], client, lemma_id, get_session_func)


def query_ukrainian_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Ukrainian verb forms."""
    return query_forms(FORM_SPECS[("uk", "verb")], client, lemma_id, get_session_func)


def query_ukrainian_adjective_declensions(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Ukrainian adjective forms."""
    return query_forms(FORM_SPECS[("uk", "adjective")], client, lemma_id, get_session_func)


def query_ukrainian_adverb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Ukrainian adverb forms."""
    return query_forms(FORM_SPECS[("uk", "adverb")], client, lemma_id, get_session_func)
