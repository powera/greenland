#!/usr/bin/python3

"""English language form generation."""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("en", "verb")].form_mapping


def query_english_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for English verb forms."""
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
