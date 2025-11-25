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
# Note: French nouns have fixed gender, so only singular/plural distinction
NOUN_FORM_MAPPING = {
    "singular": GrammaticalForm.NOUN_FR_SINGULAR,
    "plural": GrammaticalForm.NOUN_FR_PLURAL,
}

VERB_FORM_MAPPING = {
    # Present (8 persons)
    "1s_pres": GrammaticalForm.VERB_FR_1S_PRES, "2s_pres": GrammaticalForm.VERB_FR_2S_PRES,
    "3s-m_pres": GrammaticalForm.VERB_FR_3S_M_PRES, "3s-f_pres": GrammaticalForm.VERB_FR_3S_F_PRES,
    "1p_pres": GrammaticalForm.VERB_FR_1P_PRES, "2p_pres": GrammaticalForm.VERB_FR_2P_PRES,
    "3p-m_pres": GrammaticalForm.VERB_FR_3P_M_PRES, "3p-f_pres": GrammaticalForm.VERB_FR_3P_F_PRES,
    # Imperfect (8 persons)
    "1s_impf": GrammaticalForm.VERB_FR_1S_IMPF, "2s_impf": GrammaticalForm.VERB_FR_2S_IMPF,
    "3s-m_impf": GrammaticalForm.VERB_FR_3S_M_IMPF, "3s-f_impf": GrammaticalForm.VERB_FR_3S_F_IMPF,
    "1p_impf": GrammaticalForm.VERB_FR_1P_IMPF, "2p_impf": GrammaticalForm.VERB_FR_2P_IMPF,
    "3p-m_impf": GrammaticalForm.VERB_FR_3P_M_IMPF, "3p-f_impf": GrammaticalForm.VERB_FR_3P_F_IMPF,
    # Future (8 persons)
    "1s_fut": GrammaticalForm.VERB_FR_1S_FUT, "2s_fut": GrammaticalForm.VERB_FR_2S_FUT,
    "3s-m_fut": GrammaticalForm.VERB_FR_3S_M_FUT, "3s-f_fut": GrammaticalForm.VERB_FR_3S_F_FUT,
    "1p_fut": GrammaticalForm.VERB_FR_1P_FUT, "2p_fut": GrammaticalForm.VERB_FR_2P_FUT,
    "3p-m_fut": GrammaticalForm.VERB_FR_3P_M_FUT, "3p-f_fut": GrammaticalForm.VERB_FR_3P_F_FUT,
    # Passé composé (8 persons)
    "1s_pc": GrammaticalForm.VERB_FR_1S_PC, "2s_pc": GrammaticalForm.VERB_FR_2S_PC,
    "3s-m_pc": GrammaticalForm.VERB_FR_3S_M_PC, "3s-f_pc": GrammaticalForm.VERB_FR_3S_F_PC,
    "1p_pc": GrammaticalForm.VERB_FR_1P_PC, "2p_pc": GrammaticalForm.VERB_FR_2P_PC,
    "3p-m_pc": GrammaticalForm.VERB_FR_3P_M_PC, "3p-f_pc": GrammaticalForm.VERB_FR_3P_F_PC,
}


def query_french_noun_forms(client, lemma_id: int, get_session_func) -> Tuple[Dict[str, str], bool]:
    """Query LLM for French noun forms (2 genders × 2 numbers = 4 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma or not lemma.french_translation or lemma.pos_type.lower() != "noun":
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
        linguistic_db.log_query(session, word=noun, query_type="french_noun_forms", prompt=prompt,
                               response=json.dumps(response.structured_data), model=client.model)
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying French noun forms for '{noun}': {e}")
        return {}, False


def query_french_verb_conjugations(client, lemma_id: int, get_session_func) -> Tuple[Dict[str, str], bool]:
    """Query LLM for French verb conjugations (8 persons × 4 tenses = 32 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma or not lemma.french_translation or lemma.pos_type.lower() != "verb":
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
        linguistic_db.log_query(session, word=verb, query_type="french_verb_conjugations", prompt=prompt,
                               response=json.dumps(response.structured_data), model=client.model)
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying French verb conjugations for '{verb}': {e}")
        return {}, False
