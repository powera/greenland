#!/usr/bin/python3

"""Lithuanian language form generation."""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "verb")].form_mapping


def query_lithuanian_noun_declensions(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Lithuanian noun forms."""
    return query_forms(FORM_SPECS[("lt", "noun")], client, lemma_id, get_session_func)


def query_lithuanian_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Lithuanian verb forms."""
    return query_forms(FORM_SPECS[("lt", "verb")], client, lemma_id, get_session_func)


def query_lithuanian_adjective_declensions(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Lithuanian adjective forms."""
    return query_forms(FORM_SPECS[("lt", "adjective")], client, lemma_id, get_session_func)


def query_lithuanian_adverb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Lithuanian adverb forms."""
    return query_forms(FORM_SPECS[("lt", "adverb")], client, lemma_id, get_session_func)
