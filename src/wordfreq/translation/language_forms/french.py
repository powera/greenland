#!/usr/bin/python3

"""French language form generation."""

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
    "singular_m": GrammaticalForm.NOUN_FR_S_M,
    "plural_m": GrammaticalForm.NOUN_FR_P_M,
    "singular_f": GrammaticalForm.NOUN_FR_S_F,
    "plural_f": GrammaticalForm.NOUN_FR_P_F,
}

VERB_FORM_MAPPING = {
    f"{p}_{t}": getattr(GrammaticalForm, f"VERB_FR_{p.upper()}_{t.upper()}")
    for t in ["pres", "impf", "fut", "pc"]
    for p in ["1s", "2s", "3s-m", "3s-f", "1p", "2p", "3p-m", "3p-f"]
}


def query_french_noun_forms(client, lemma_id: int, get_session_func) -> Tuple[Dict[str, str], bool]:
    """Query LLM for French noun forms (2 genders × 2 numbers = 4 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma or not lemma.french_translation or lemma.pos_type.lower() != 'noun':
        logger.error(f"Invalid lemma for French noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = lemma.french_translation, lemma.lemma_text, lemma.definition_text, lemma.pos_subtype
    fields = ["singular_m", "plural_m", "singular_f", "plural_f"]
    form_properties = {f: SchemaProperty("string", f"French {f.replace('_', ' ')}") for f in fields}

    schema = Schema(name="FrenchNounForms", description="French noun forms", properties={
        "forms": SchemaProperty("object", "Dictionary of noun forms", properties=form_properties),
        "confidence": SchemaProperty("number", "Confidence 0-1"), "notes": SchemaProperty("string", "Notes")})

    try:
        context = util.prompt_loader.get_context("wordfreq", "french_noun_forms")
        prompt = util.prompt_loader.get_prompt("wordfreq", "french_noun_forms").format(
            noun=noun, english_noun=english_noun, definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "")
        response = client.generate_chat(prompt=prompt, model=client.model, json_schema=schema, context=context)
        linguistic_db.log_query(session, word=noun, query_type='french_noun_forms', prompt=prompt,
                               response=json.dumps(response.structured_data), model=client.model)
        if response.structured_data and 'forms' in response.structured_data:
            return response.structured_data['forms'], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying French noun forms for '{noun}': {e}")
        return {}, False


def query_french_verb_conjugations(client, lemma_id: int, get_session_func) -> Tuple[Dict[str, str], bool]:
    """Query LLM for French verb conjugations (8 persons × 4 tenses = 32 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma or not lemma.french_translation or lemma.pos_type.lower() != 'verb':
        logger.error(f"Invalid lemma for French verb conjugations: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = lemma.french_translation, lemma.lemma_text, lemma.definition_text, lemma.pos_subtype
    tenses = [("pres", "present"), ("impf", "imperfect"), ("fut", "future"), ("pc", "passé composé")]
    fields = [f"{p}_{t}" for t, _ in tenses for p in ["1s", "2s", "3s-m", "3s-f", "1p", "2p", "3p-m", "3p-f"]]
    form_properties = {f: SchemaProperty("string", f"French {f.replace('_', ' ')}") for f in fields}

    schema = Schema(name="FrenchVerbConjugations", description="French verb conjugations", properties={
        "forms": SchemaProperty("object", "Dictionary of verb forms", properties=form_properties),
        "confidence": SchemaProperty("number", "Confidence 0-1"), "notes": SchemaProperty("string", "Notes")})

    try:
        context = util.prompt_loader.get_context("wordfreq", "french_verb_conjugations")
        prompt = util.prompt_loader.get_prompt("wordfreq", "french_verb_conjugations").format(
            verb=verb, english_verb=english_verb, definition=definition,
            subtype_context=f" (category: {pos_subtype})" if pos_subtype else "")
        response = client.generate_chat(prompt=prompt, model=client.model, json_schema=schema, context=context)
        linguistic_db.log_query(session, word=verb, query_type='french_verb_conjugations', prompt=prompt,
                               response=json.dumps(response.structured_data), model=client.model)
        if response.structured_data and 'forms' in response.structured_data:
            return response.structured_data['forms'], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying French verb conjugations for '{verb}': {e}")
        return {}, False
