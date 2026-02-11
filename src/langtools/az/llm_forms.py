#!/usr/bin/python3

"""Azerbaijani language form generation."""

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
    "singular": GrammaticalForm.NOUN_AZ_SINGULAR,
    "plural": GrammaticalForm.NOUN_AZ_PLURAL,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "present": GrammaticalForm.VERB_AZ_PRESENT,
    "past": GrammaticalForm.VERB_AZ_PAST,
    "future": GrammaticalForm.VERB_AZ_FUTURE,
}


def query_azerbaijani_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Azerbaijani noun forms (singular and plural)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    azerbaijani_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "az",
        )
        .first()
    )

    if not lemma or not azerbaijani_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Azerbaijani noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        azerbaijani_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["singular", "plural"]
    form_properties = {f: SchemaProperty("string", f"Azerbaijani {f}") for f in fields}

    schema = Schema(
        name="AzerbaijaniNounForms",
        description="Azerbaijani noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "azerbaijani/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "azerbaijani/noun").format(
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
            query_type="azerbaijani_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Azerbaijani noun forms for '{noun}': {e}")
        return {}, False


def query_azerbaijani_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Azerbaijani verb forms (present, past, future)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    azerbaijani_translation = get_translation(session, lemma, "az") if lemma else None

    if not lemma or not azerbaijani_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Azerbaijani verb forms: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        azerbaijani_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["present", "past", "future"]
    form_properties = {f: SchemaProperty("string", f"Azerbaijani {f} form") for f in fields}

    schema = Schema(
        name="AzerbaijaniVerbForms",
        description="Azerbaijani verb forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "azerbaijani/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "azerbaijani/verb").format(
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
            query_type="azerbaijani_verb_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Azerbaijani verb forms for '{verb}': {e}")
        return {}, False
