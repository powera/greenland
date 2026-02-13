#!/usr/bin/python3

"""Thai language form generation — thin shim over form_registry.

All form specifications are derived from ``th/forms_config.py`` via
:mod:`langtools.form_registry`.  This module re-exports the mappings
and query functions for backward compatibility.
"""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

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
