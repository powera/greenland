"""Kannada language form generation — thin shim over form_registry.

All form specifications are derived from ``kn/forms_config.py`` via
:mod:`langtools.form_registry`.  This module re-exports the mappings
and query functions for backward compatibility.
"""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

# Re-export form mappings from FORM_SPECS
ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("kn", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("kn", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("kn", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("kn", "verb")].form_mapping


def query_kannada_noun_declensions(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    return query_forms(FORM_SPECS[("kn", "noun")], client, lemma_id, get_session_func)


def query_kannada_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    return query_forms(FORM_SPECS[("kn", "verb")], client, lemma_id, get_session_func)


def query_kannada_adjective_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    return query_forms(FORM_SPECS[("kn", "adjective")], client, lemma_id, get_session_func)


def query_kannada_adverb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    return query_forms(FORM_SPECS[("kn", "adverb")], client, lemma_id, get_session_func)
