#!/usr/bin/python3

"""Japanese language form generation."""

from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from sqlalchemy.orm import Session
from storage.models.enums import GrammaticalForm

NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("ja", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("ja", "verb")].form_mapping


def query_japanese_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Japanese noun forms."""
    return query_forms(FORM_SPECS[("ja", "noun")], client, lemma_id, get_session_func)


def query_japanese_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Japanese verb forms."""
    return query_forms(FORM_SPECS[("ja", "verb")], client, lemma_id, get_session_func)
