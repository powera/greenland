#!/usr/bin/python3

"""Polish language form generation — thin shim over form_registry.

All form specifications are derived from ``pl/forms_config.py`` via
:mod:`langtools.form_registry`.  This module re-exports the mappings
and query functions for backward compatibility.
"""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pl", "adjective")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pl", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("pl", "verb")].form_mapping


def query_polish_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Polish noun forms."""
    return query_forms(FORM_SPECS[("pl", "noun")], client, lemma_id, get_session_func)


def query_polish_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Polish verb forms."""
    return query_forms(FORM_SPECS[("pl", "verb")], client, lemma_id, get_session_func)


def query_polish_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Polish adjective forms."""
    return query_forms(FORM_SPECS[("pl", "adjective")], client, lemma_id, get_session_func)
