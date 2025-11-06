#!/usr/bin/python3

"""German language form generation."""

import json
import logging
from typing import Dict, Tuple

from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.enums import GrammaticalForm
import util.prompt_loader
from wordfreq.storage import database as linguistic_db

logger = logging.getLogger(__name__)

# Form mappings
NOUN_FORM_MAPPING = {
    "singular": GrammaticalForm.NOUN_DE_SINGULAR,
    "plural": GrammaticalForm.NOUN_DE_PLURAL,
}

VERB_FORM_MAPPING = {
    # Present (8 persons)
    "1s_pres": GrammaticalForm.VERB_DE_1S_PRES, "2s_pres": GrammaticalForm.VERB_DE_2S_PRES,
    "3s-m_pres": GrammaticalForm.VERB_DE_3S_M_PRES, "3s-f_pres": GrammaticalForm.VERB_DE_3S_F_PRES,
    "1p_pres": GrammaticalForm.VERB_DE_1P_PRES, "2p_pres": GrammaticalForm.VERB_DE_2P_PRES,
    "3p-m_pres": GrammaticalForm.VERB_DE_3P_M_PRES, "3p-f_pres": GrammaticalForm.VERB_DE_3P_F_PRES,
    # Past (Perfect - compound past) (8 persons)
    "1s_past": GrammaticalForm.VERB_DE_1S_PAST, "2s_past": GrammaticalForm.VERB_DE_2S_PAST,
    "3s-m_past": GrammaticalForm.VERB_DE_3S_M_PAST, "3s-f_past": GrammaticalForm.VERB_DE_3S_F_PAST,
    "1p_past": GrammaticalForm.VERB_DE_1P_PAST, "2p_past": GrammaticalForm.VERB_DE_2P_PAST,
    "3p-m_past": GrammaticalForm.VERB_DE_3P_M_PAST, "3p-f_past": GrammaticalForm.VERB_DE_3S_F_PAST,
    # Future (8 persons)
    "1s_fut": GrammaticalForm.VERB_DE_1S_FUT, "2s_fut": GrammaticalForm.VERB_DE_2S_FUT,
    "3s-m_fut": GrammaticalForm.VERB_DE_3S_M_FUT, "3s-f_fut": GrammaticalForm.VERB_DE_3S_F_FUT,
    "1p_fut": GrammaticalForm.VERB_DE_1P_FUT, "2p_fut": GrammaticalForm.VERB_DE_2P_FUT,
    "3p-m_fut": GrammaticalForm.VERB_DE_3P_M_FUT, "3p-f_fut": GrammaticalForm.VERB_DE_3P_F_FUT,
}


def query_german_noun_forms(client, lemma_id: int, get_session_func) -> Tuple[Dict[str, str], bool]:
    """Query LLM for German noun forms (singular and plural)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    # Get German translation from lemma_translations table
    german_translation = session.query(linguistic_db.LemmaTranslation).filter(
        linguistic_db.LemmaTranslation.lemma_id == lemma_id,
        linguistic_db.LemmaTranslation.language_code == 'de'
    ).first()

    if not lemma or not german_translation or lemma.pos_type.lower() != 'noun':
        logger.error(f"Invalid lemma for German noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = german_translation.translation, lemma.lemma_text, lemma.definition_text, lemma.pos_subtype
    fields = ["singular", "plural"]
    form_properties = {f: SchemaProperty("string", f"German {f}") for f in fields}

    schema = Schema(name="GermanNounForms", description="German noun forms", properties={
        "forms": SchemaProperty("object", "Dictionary of noun forms", properties=form_properties),
        "confidence": SchemaProperty("number", "Confidence 0-1"),
        "notes": SchemaProperty("string", "Notes")})

    try:
        context = util.prompt_loader.get_context("wordfreq", "german_noun_forms")
        prompt = util.prompt_loader.get_prompt("wordfreq", "german_noun_forms").format(
            noun=noun, english_noun=english_noun, definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "")
        response = client.generate_chat(prompt=prompt, model=client.model, json_schema=schema, context=context)
        linguistic_db.log_query(session, word=noun, query_type='german_noun_forms', prompt=prompt,
                               response=json.dumps(response.structured_data), model=client.model)
        if response.structured_data and 'forms' in response.structured_data:
            return response.structured_data['forms'], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying German noun forms for '{noun}': {e}")
        return {}, False


def query_german_verb_conjugations(client, lemma_id: int, get_session_func) -> Tuple[Dict[str, str], bool]:
    """Query LLM for German verb conjugations (8 persons × 3 tenses = 24 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()

    # Get German translation from lemma_translations table
    german_translation = session.query(linguistic_db.LemmaTranslation).filter(
        linguistic_db.LemmaTranslation.lemma_id == lemma_id,
        linguistic_db.LemmaTranslation.language_code == 'de'
    ).first()

    if not lemma or not german_translation or lemma.pos_type.lower() != 'verb':
        logger.error(f"Invalid lemma for German verb conjugations: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = german_translation.translation, lemma.lemma_text, lemma.definition_text, lemma.pos_subtype
    tenses = [("pres", "present"), ("past", "past"), ("fut", "future")]
    fields = [f"{p}_{t}" for t, _ in tenses for p in ["1s", "2s", "3s-m", "3s-f", "1p", "2p", "3p-m", "3p-f"]]
    form_properties = {f: SchemaProperty("string", f"German {f.replace('_', ' ')}") for f in fields}

    schema = Schema(name="GermanVerbConjugations", description="German verb conjugations", properties={
        "forms": SchemaProperty("object", "Dictionary of verb forms", properties=form_properties),
        "confidence": SchemaProperty("number", "Confidence 0-1"),
        "notes": SchemaProperty("string", "Notes")})

    try:
        context = util.prompt_loader.get_context("wordfreq", "german_verb_conjugations")
        prompt = util.prompt_loader.get_prompt("wordfreq", "german_verb_conjugations").format(
            verb=verb, english_verb=english_verb, definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "")
        response = client.generate_chat(prompt=prompt, model=client.model, json_schema=schema, context=context)
        linguistic_db.log_query(session, word=verb, query_type='german_verb_conjugations', prompt=prompt,
                               response=json.dumps(response.structured_data), model=client.model)
        if response.structured_data and 'forms' in response.structured_data:
            return response.structured_data['forms'], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying German verb conjugations for '{verb}': {e}")
        return {}, False
