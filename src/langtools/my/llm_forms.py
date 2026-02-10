#!/usr/bin/python3

"""Burmese language form generation."""

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
    "singular": GrammaticalForm.NOUN_MY_SINGULAR,
    "plural": GrammaticalForm.NOUN_MY_PLURAL,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "present": GrammaticalForm.VERB_MY_PRESENT,
    "past": GrammaticalForm.VERB_MY_PAST,
    "future": GrammaticalForm.VERB_MY_FUTURE,
}


def query_burmese_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Burmese noun forms (singular and plural)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    burmese_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "my",
        )
        .first()
    )

    if not lemma or not burmese_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Burmese noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        burmese_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["singular", "plural"]
    form_properties = {f: SchemaProperty("string", f"Burmese {f}") for f in fields}

    schema = Schema(
        name="BurmeseNounForms",
        description="Burmese noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "burmese/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "burmese/noun").format(
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
            query_type="burmese_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Burmese noun forms for '{noun}': {e}")
        return {}, False


def query_burmese_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Burmese verb forms (present, past, future constructions)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    burmese_translation = get_translation(session, lemma, "my") if lemma else None

    if not lemma or not burmese_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Burmese verb forms: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        burmese_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["present", "past", "future"]
    form_properties = {f: SchemaProperty("string", f"Burmese {f} form") for f in fields}

    schema = Schema(
        name="BurmeseVerbForms",
        description="Burmese verb forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "burmese/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "burmese/verb").format(
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
            query_type="burmese_verb_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Burmese verb forms for '{verb}': {e}")
        return {}, False
