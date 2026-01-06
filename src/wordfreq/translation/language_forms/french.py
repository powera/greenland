#!/usr/bin/python3

"""French language form generation."""

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
# Note: French nouns have fixed gender, so only singular/plural distinction
NOUN_FORM_MAPPING = {
    "singular": GrammaticalForm.NOUN_FR_SINGULAR,
    "plural": GrammaticalForm.NOUN_FR_PLURAL,
}

VERB_FORM_MAPPING = {
    # Present (6 persons)
    "1s_present": GrammaticalForm.VERB_FR_1S_PRESENT,
    "2s_present": GrammaticalForm.VERB_FR_2S_PRESENT,
    "3s_present": GrammaticalForm.VERB_FR_3S_PRESENT,
    "1p_present": GrammaticalForm.VERB_FR_1P_PRESENT,
    "2p_present": GrammaticalForm.VERB_FR_2P_PRESENT,
    "3p_present": GrammaticalForm.VERB_FR_3P_PRESENT,
    # Imperfect (6 persons)
    "1s_impf": GrammaticalForm.VERB_FR_1S_IMPF,
    "2s_impf": GrammaticalForm.VERB_FR_2S_IMPF,
    "3s_impf": GrammaticalForm.VERB_FR_3S_IMPF,
    "1p_impf": GrammaticalForm.VERB_FR_1P_IMPF,
    "2p_impf": GrammaticalForm.VERB_FR_2P_IMPF,
    "3p_impf": GrammaticalForm.VERB_FR_3P_IMPF,
    # Future (6 persons)
    "1s_future": GrammaticalForm.VERB_FR_1S_FUTURE,
    "2s_future": GrammaticalForm.VERB_FR_2S_FUTURE,
    "3s_future": GrammaticalForm.VERB_FR_3S_FUTURE,
    "1p_future": GrammaticalForm.VERB_FR_1P_FUTURE,
    "2p_future": GrammaticalForm.VERB_FR_2P_FUTURE,
    "3p_future": GrammaticalForm.VERB_FR_3P_FUTURE,
    # Passé composé (2 past participle forms)
    "pc_m": GrammaticalForm.VERB_FR_PC_M,
    "pc_f": GrammaticalForm.VERB_FR_PC_F,
}


def query_french_noun_forms(client, lemma_id: int, get_session_func) -> Tuple[Dict[str, str], bool]:
    """Query LLM for French noun forms (singular and plural for the noun's gender)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    french_translation = get_translation(session, lemma, "fr") if lemma else None
    if not lemma or not french_translation or lemma.pos_type.lower() != "noun":
        logger.error(f"Invalid lemma for French noun forms: {lemma_id}")
        return {}, False

    noun, english_noun, definition, pos_subtype = (
        french_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )

    # Schema for getting both forms AND gender
    fields = ["singular", "plural"]
    form_properties = {f: SchemaProperty("string", f"French {f}") for f in fields}

    schema = Schema(
        name="FrenchNounForms",
        description="French noun forms with gender",
        properties={
            "gender": SchemaProperty("string", "Gender: 'masculine' or 'feminine'"),
            "forms": SchemaProperty(
                "object", "Dictionary of noun forms (singular and plural)", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("wordfreq", "french_noun_forms")
        prompt = util.prompt_loader.get_prompt("wordfreq", "french_noun_forms").format(
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
            query_type="french_noun_forms",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying French noun forms for '{noun}': {e}")
        return {}, False


def query_french_verb_conjugations(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """Query LLM for French verb conjugations (6 persons × 3 tenses + 2 past participles = 20 forms)."""
    session = get_session_func()
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    french_translation = get_translation(session, lemma, "fr") if lemma else None
    if not lemma or not french_translation or lemma.pos_type.lower() != "verb":
        logger.error(f"Invalid lemma for French verb conjugations: {lemma_id}")
        return {}, False

    verb, english_verb, definition, pos_subtype = (
        french_translation,
        lemma.lemma_text,
        lemma.definition_text,
        lemma.pos_subtype,
    )
    # 6 persons for present, imperfect, future
    regular_tenses = [("present", "present"), ("impf", "imperfect"), ("future", "future")]
    fields = [
        f"{p}_{t}"
        for t, _ in regular_tenses
        for p in ["1s", "2s", "3s", "1p", "2p", "3p"]
    ]
    # Add past participle forms (masculine and feminine)
    fields.extend(["pc_m", "pc_f"])
    form_properties = {f: SchemaProperty("string", f"French {f.replace('_', ' ')}") for f in fields}

    schema = Schema(
        name="FrenchVerbConjugations",
        description="French verb conjugations",
        properties={
            "forms": SchemaProperty(
                "object", "Dictionary of verb forms", properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence 0-1"),
            "notes": SchemaProperty("string", "Notes"),
        },
    )

    try:
        context = util.prompt_loader.get_context("wordfreq", "french_verb_conjugations")
        prompt = util.prompt_loader.get_prompt("wordfreq", "french_verb_conjugations").format(
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
            query_type="french_verb_conjugations",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=client.default_model,
        )
        if response.structured_data and "forms" in response.structured_data:
            return response.structured_data["forms"], True
        return {}, False
    except Exception as e:
        logger.error(f"Error querying French verb conjugations for '{verb}': {e}")
        return {}, False
