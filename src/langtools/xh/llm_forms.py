#!/usr/bin/python3

"""Xhosa language form generation."""

import json
import logging
from typing import Callable, Dict, Tuple

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from clients.unified_client import UnifiedLLMClient
from sqlalchemy.orm import Session
from storage import database as linguistic_db
from storage.models.enums import GrammaticalForm
from storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

# Form mappings
NOUN_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "singular": GrammaticalForm.NOUN_XH_SINGULAR,
    "plural": GrammaticalForm.NOUN_XH_PLURAL,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "present": GrammaticalForm.VERB_XH_PRESENT,
    "past": GrammaticalForm.VERB_XH_PAST,
    "future": GrammaticalForm.VERB_XH_FUTURE,
}


def query_xhosa_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Xhosa noun forms (singular and plural)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    xhosa_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "xh",
        )
        .first()
    )

    if not lemma or not xhosa_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Xhosa noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        xhosa_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["singular", "plural"]
    form_properties = {f: SchemaProperty("string", f"Xhosa {f}") for f in fields}

    schema = Schema(
        name="XhosaNounForms",
        description="Xhosa noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "xhosa/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "xhosa/noun").format(
            noun=noun,
            english_noun=english_noun,
            definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "",
        )
        response = client.generate_chat(
            prompt=prompt,
            model=client.default_model,
            json_schema=schema,
            context=context,
        )
        linguistic_db.log_query(
            session,
            word=noun,
            query_type="xhosa_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Xhosa noun forms for '{noun}': {e}")
        return {}, False


def query_xhosa_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Xhosa verb forms (present, past, future constructions)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    xhosa_translation = get_translation(session, lemma, "xh") if lemma else None

    if not lemma or not xhosa_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Xhosa verb forms: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        xhosa_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["present", "past", "future"]
    form_properties = {f: SchemaProperty("string", f"Xhosa {f} form") for f in fields}

    schema = Schema(
        name="XhosaVerbForms",
        description="Xhosa verb forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "xhosa/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "xhosa/verb").format(
            verb=verb,
            english_verb=english_verb,
            definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "",
        )
        response = client.generate_chat(
            prompt=prompt,
            model=client.default_model,
            json_schema=schema,
            context=context,
        )
        linguistic_db.log_query(
            session,
            word=verb,
            query_type="xhosa_verb_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Xhosa verb forms for '{verb}': {e}")
        return {}, False
