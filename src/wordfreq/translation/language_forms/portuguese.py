#!/usr/bin/python3

"""Portuguese language form generation."""

import json
import logging
from typing import Dict, Tuple

from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.enums import GrammaticalForm
import util.prompt_loader
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.translation_helpers import get_translation

logger = logging.getLogger(__name__)

# Form mappings
NOUN_FORM_MAPPING = {
    "singular": GrammaticalForm.NOUN_PT_SINGULAR,
    "plural": GrammaticalForm.NOUN_PT_PLURAL,
}

VERB_FORM_MAPPING = {
    # Present (6 persons)
    "1s_present": GrammaticalForm.VERB_PT_1S_PRESENT,
    "2s_present": GrammaticalForm.VERB_PT_2S_PRESENT,
    "3s_present": GrammaticalForm.VERB_PT_3S_PRESENT,
    "1p_present": GrammaticalForm.VERB_PT_1P_PRESENT,
    "2p_present": GrammaticalForm.VERB_PT_2P_PRESENT,
    "3p_present": GrammaticalForm.VERB_PT_3P_PRESENT,
    # Past (6 persons)
    "1s_past": GrammaticalForm.VERB_PT_1S_PAST,
    "2s_past": GrammaticalForm.VERB_PT_2S_PAST,
    "3s_past": GrammaticalForm.VERB_PT_3S_PAST,
    "1p_past": GrammaticalForm.VERB_PT_1P_PAST,
    "2p_past": GrammaticalForm.VERB_PT_2P_PAST,
    "3p_past": GrammaticalForm.VERB_PT_3P_PAST,
    # Future (6 persons)
    "1s_future": GrammaticalForm.VERB_PT_1S_FUTURE,
    "2s_future": GrammaticalForm.VERB_PT_2S_FUTURE,
    "3s_future": GrammaticalForm.VERB_PT_3S_FUTURE,
    "1p_future": GrammaticalForm.VERB_PT_1P_FUTURE,
    "2p_future": GrammaticalForm.VERB_PT_2P_FUTURE,
    "3p_future": GrammaticalForm.VERB_PT_3P_FUTURE,
}


def query_portuguese_noun_forms(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Portuguese noun forms (singular and plural)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    # Get Portuguese translation from lemma_translations table
    portuguese_translation = (
        session.query(linguistic_db.LemmaTranslation)
        .filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma_id,
            linguistic_db.LemmaTranslation.language_code == "pt",
        )
        .first()
    )

    if not lemma or not portuguese_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for Portuguese noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        portuguese_translation.translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    fields = ["singular", "plural"]
    form_properties = {f: SchemaProperty("string", f"Portuguese {f}") for f in fields}

    schema = Schema(
        name="PortugueseNounForms",
        description="Portuguese noun forms",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("wordfreq", "portuguese_noun_forms")
        prompt = util.prompt_loader.get_prompt("wordfreq", "portuguese_noun_forms").format(
            noun=noun,
            english_noun=english_noun,
            definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "",
        )
        response = client.generate_chat(
            prompt=prompt, model=client.default_model, json_schema=schema, context=context
        )
        linguistic_db.log_query(
            session,
            word=noun,
            query_type="portuguese_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Portuguese noun forms for '{noun}': {e}")
        return {}, False


def query_portuguese_verb_conjugations(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for Portuguese verb conjugations (6 persons × 3 tenses = 18 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    portuguese_translation = get_translation(session, lemma, "pt") if lemma else None

    if not lemma or not portuguese_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for Portuguese verb conjugations: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        portuguese_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    tenses = [("present", "present"), ("past", "past"), ("future", "future")]
    fields = [f"{p}_{t}" for t, _ in tenses for p in ["1s", "2s", "3s", "1p", "2p", "3p"]]
    form_properties = {
        f: SchemaProperty("string", f"Portuguese {f.replace('_', ' ')}") for f in fields
    }

    schema = Schema(
        name="PortugueseVerbConjugations",
        description="Portuguese verb conjugations",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("wordfreq", "portuguese_verb_conjugations")
        prompt = util.prompt_loader.get_prompt("wordfreq", "portuguese_verb_conjugations").format(
            verb=verb,
            english_verb=english_verb,
            definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "",
        )
        response = client.generate_chat(
            prompt=prompt, model=client.default_model, json_schema=schema, context=context
        )
        linguistic_db.log_query(
            session,
            word=verb,
            query_type="portuguese_verb_conjugations",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying Portuguese verb conjugations for '{verb}': {e}")
        return {}, False
