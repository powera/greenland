#!/usr/bin/python3

"""Lithuanian language form generation."""

import json
import logging
import re
from typing import Callable, Dict, Tuple

from clients.unified_client import UnifiedLLMClient
from langtools.form_registry import FORM_SPECS
from langtools.llm_forms_base import query_forms
from langtools.lt.conjugation import conjugate_verb
from langtools.lt.principal_parts import get_principal_parts
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

ADJECTIVE_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "adjective")].form_mapping
ADVERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "adverb")].form_mapping
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "noun")].form_mapping
VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = FORM_SPECS[("lt", "verb")].form_mapping


def _parse_principal_parts(translation_text: str) -> Tuple[str, str, str] | None:
    """Parse Lithuanian translation text that includes principal parts.

    Supported formats:
    - "dirbti, dirba, dirbo"
    - "dirbti (dirba, dirbo)"
    """
    candidate_text = translation_text.strip()
    with_parentheses_match = re.match(r"^([^()]+)\(([^()]+)\)$", candidate_text)
    if with_parentheses_match:
        infinitive = with_parentheses_match.group(1).strip().rstrip(",")
        parts_text = with_parentheses_match.group(2).strip()
        parts = [part.strip() for part in parts_text.split(",") if part.strip()]
        if len(parts) == 2:
            return infinitive, parts[0], parts[1]

    parts = [part.strip() for part in candidate_text.split(",") if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]

    return None


def query_lithuanian_noun_declensions(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Lithuanian noun forms."""
    return query_forms(FORM_SPECS[("lt", "noun")], client, lemma_id, get_session_func)


def query_lithuanian_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Generate Lithuanian verb forms mechanically when possible, else use LLM."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    if lemma and lemma.pos_type.lower() == "verb":
        lithuanian_verb = get_translation(session, lemma, "lt")
        if lithuanian_verb:
            # Try principal parts from grammar facts DB
            release_parts = get_principal_parts(session, lemma.guid) if lemma.guid else None
            if release_parts:
                principal_parts: Tuple[str, str, str] | None = (
                    lithuanian_verb.strip(),
                    release_parts[0],
                    release_parts[1],
                )
            else:
                # Fall back to parsing principal parts from the translation string
                principal_parts = _parse_principal_parts(lithuanian_verb)

            if principal_parts:
                conjugation_forms = conjugate_verb(*principal_parts)
                if conjugation_forms:
                    source = "grammar_facts DB" if release_parts else "translation principal parts"
                    linguistic_db.log_query(
                        session,
                        word=lithuanian_verb,
                        query_type="lithuanian_verb_forms",
                        prompt="[mechanical langtools.lt.conjugation]",
                        response=json.dumps(
                            {
                                "forms": conjugation_forms,
                                "notes": f"mechanical from {source}",
                                "mechanical": True,
                            }
                        ),
                        model=client.default_model,
                    )
                    return conjugation_forms, True
            logger.info("Falling back to LLM for Lithuanian verb '%s'", lithuanian_verb)

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
