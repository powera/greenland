#!/usr/bin/python3

"""Vietnamese language form generation.

Vietnamese is an isolating language: nouns and verbs have no inflectional
morphology.  The "forms" stored here are simply the base dictionary entry,
which lets the rest of the pipeline treat Vietnamese the same as any other
language without special-casing.
"""

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
    "base": GrammaticalForm.NOUN_VI_BASE,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    "base": GrammaticalForm.VERB_VI_BASE,
}


def query_vietnamese_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Vietnamese noun forms (base form only)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    vi_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "vi",
        )
        .first()
    )

    if not lemma or not vi_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Vietnamese noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        vi_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["base"]
    form_properties = {f: SchemaProperty("string", f"Vietnamese {f} form") for f in fields}

    schema = Schema(
        name="VietnameseNounForms",
        description="Vietnamese noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "vietnamese/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "vietnamese/noun").format(
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
            query_type="vietnamese_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Vietnamese noun forms for '{noun}': {e}")
        return {}, False


def query_vietnamese_verb_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Vietnamese verb forms (base form only)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    vi_translation = get_translation(session, lemma, "vi") if lemma else None

    if not lemma or not vi_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Vietnamese verb forms: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        vi_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["base"]
    form_properties = {f: SchemaProperty("string", f"Vietnamese {f} form") for f in fields}

    schema = Schema(
        name="VietnameseVerbForms",
        description="Vietnamese verb forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "vietnamese/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "vietnamese/verb").format(
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
            query_type="vietnamese_verb_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Vietnamese verb forms for '{verb}': {e}")
        return {}, False
