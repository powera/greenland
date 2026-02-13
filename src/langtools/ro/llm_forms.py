#!/usr/bin/python3

"""Romanian language form generation — thin shim over form_registry.

All form specifications are derived from ``ro/forms_config.py`` via
:mod:`langtools.form_registry`.  This module re-exports the mappings
and query functions for backward compatibility.
"""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("ro", "adjective")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("ro", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("ro", "verb")].form_mapping


def query_romanian_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Romanian noun forms."""
    return query_forms(FORM_SPECS[("ro", "noun")], client, lemma_id, get_session_func)


def query_romanian_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Romanian verb forms."""
    return query_forms(FORM_SPECS[("ro", "verb")], client, lemma_id, get_session_func)


def query_romanian_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Romanian adjective forms."""
    return query_forms(FORM_SPECS[("ro", "adjective")], client, lemma_id, get_session_func)
