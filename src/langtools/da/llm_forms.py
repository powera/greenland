#!/usr/bin/python3

"""Danish language form generation."""

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
    "singular": GrammaticalForm.NOUN_DA_SINGULAR,
    "plural": GrammaticalForm.NOUN_DA_PLURAL,
}

VERB_FORM_MAPPING: Dict[str, GrammaticalForm] = {
    # Present (6 persons - Danish verbs don't conjugate by person,
    # but we use the standard schema for consistency)
    "1s_present": GrammaticalForm.VERB_DA_1S_PRESENT,
    "2s_present": GrammaticalForm.VERB_DA_2S_PRESENT,
    "3s_present": GrammaticalForm.VERB_DA_3S_PRESENT,
    "1p_present": GrammaticalForm.VERB_DA_1P_PRESENT,
    "2p_present": GrammaticalForm.VERB_DA_2P_PRESENT,
    "3p_present": GrammaticalForm.VERB_DA_3P_PRESENT,
    # Past (6 persons)
    "1s_past": GrammaticalForm.VERB_DA_1S_PAST,
    "2s_past": GrammaticalForm.VERB_DA_2S_PAST,
    "3s_past": GrammaticalForm.VERB_DA_3S_PAST,
    "1p_past": GrammaticalForm.VERB_DA_1P_PAST,
    "2p_past": GrammaticalForm.VERB_DA_2P_PAST,
    "3p_past": GrammaticalForm.VERB_DA_3P_PAST,
    # Future (6 persons)
    "1s_future": GrammaticalForm.VERB_DA_1S_FUTURE,
    "2s_future": GrammaticalForm.VERB_DA_2S_FUTURE,
    "3s_future": GrammaticalForm.VERB_DA_3S_FUTURE,
    "1p_future": GrammaticalForm.VERB_DA_1P_FUTURE,
    "2p_future": GrammaticalForm.VERB_DA_2P_FUTURE,
    "3p_future": GrammaticalForm.VERB_DA_3P_FUTURE,
}


def query_danish_noun_forms(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Danish noun forms (singular and plural)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    danish_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "da",
        )
        .first()
    )

    if not lemma or not danish_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Danish noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        danish_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["singular", "plural"]
    form_properties = {f: SchemaProperty("string", f"Danish {f}") for f in fields}

    schema = Schema(
        name="DanishNounForms",
        description="Danish noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "danish/noun")
        prompt = util.prompt_loader.get_prompt("language_forms", "danish/noun").format(
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
            query_type="danish_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Danish noun forms for '{noun}': {e}")
        return {}, False


def query_danish_verb_conjugations(
    client: UnifiedLLMClient, lemma_id: int, get_session_func: Callable[[], Session]
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Danish verb conjugations (6 persons x 3 tenses = 18 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    danish_translation = get_translation(session, lemma, "da") if lemma else None

    if not lemma or not danish_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Danish verb conjugations: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        danish_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    tenses = [("present", "present"), ("past", "past"), ("future", "future")]
    fields = [f"{p}_{t}" for t, _ in tenses for p in ["1s", "2s", "3s", "1p", "2p", "3p"]]
    form_properties = {f: SchemaProperty("string", f"Danish {f.replace('_', ' ')}") for f in fields}

    schema = Schema(
        name="DanishVerbConjugations",
        description="Danish verb conjugations",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("language_forms", "danish/verb")
        prompt = util.prompt_loader.get_prompt("language_forms", "danish/verb").format(
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
            query_type="danish_verb_conjugations",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Danish verb conjugations for '{verb}': {e}")
        return {}, False
