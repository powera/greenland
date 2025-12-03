#!/usr/bin/python3

"""English language form generation."""

import json
import logging
from typing import Dict, Tuple

from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.enums import GrammaticalForm
import util.prompt_loader
from wordfreq.storage import database as linguistic_db

logger = logging.getLogger(__name__)

# Form mapping for English verbs
VERB_FORM_MAPPING = {
    "1s_pres": GrammaticalForm.VERB_EN_1S_PRES,
    "2s_pres": GrammaticalForm.VERB_EN_2S_PRES,
    "3s_pres": GrammaticalForm.VERB_EN_3S_PRES,
    "1p_pres": GrammaticalForm.VERB_EN_1P_PRES,
    "2p_pres": GrammaticalForm.VERB_EN_2P_PRES,
    "3p_pres": GrammaticalForm.VERB_EN_3P_PRES,
    "1s_past": GrammaticalForm.VERB_EN_1S_PAST,
    "2s_past": GrammaticalForm.VERB_EN_2S_PAST,
    "3s_past": GrammaticalForm.VERB_EN_3S_PAST,
    "1p_past": GrammaticalForm.VERB_EN_1P_PAST,
    "2p_past": GrammaticalForm.VERB_EN_2P_PAST,
    "3p_past": GrammaticalForm.VERB_EN_3P_PAST,
    "1s_fut": GrammaticalForm.VERB_EN_1S_FUT,
    "2s_fut": GrammaticalForm.VERB_EN_2S_FUT,
    "3s_fut": GrammaticalForm.VERB_EN_3S_FUT,
    "1p_fut": GrammaticalForm.VERB_EN_1P_FUT,
    "2p_fut": GrammaticalForm.VERB_EN_2P_FUT,
    "3p_fut": GrammaticalForm.VERB_EN_3P_FUT,
    "2s_imp": GrammaticalForm.VERB_EN_2S_IMP,
    "2p_imp": GrammaticalForm.VERB_EN_2P_IMP,
}


def query_english_verb_conjugations(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM for all English verb conjugations (3 tenses × 6 persons + 2 imperatives).

    Args:
        client: UnifiedLLMClient instance
        lemma_id: The ID of the lemma to generate conjugations for
        get_session_func: Function to get database session

    Returns:
        Tuple of (dict mapping form names to conjugations, success flag)
    """
    session = get_session_func()

    # Get the lemma
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma:
        logger.error(f"Lemma with ID {lemma_id} not found")
        return {}, False

    if lemma.pos_type.lower() != "verb":
        logger.error(f"Lemma ID {lemma_id} is not a verb (pos_type: {lemma.pos_type})")
        return {}, False

    verb = lemma.lemma_text
    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # All 20 forms (3 tenses × 6 persons + 2 imperatives)
    present_fields = ["1s_pres", "2s_pres", "3s_pres", "1p_pres", "2p_pres", "3p_pres"]
    past_fields = ["1s_past", "2s_past", "3s_past", "1p_past", "2p_past", "3p_past"]
    future_fields = ["1s_fut", "2s_fut", "3s_fut", "1p_fut", "2p_fut", "3p_fut"]
    imperative_fields = ["2s_imp", "2p_imp"]

    # Build schema properties for all forms
    form_properties = {}
    for form in present_fields + past_fields + future_fields + imperative_fields:
        form_properties[form] = SchemaProperty(
            "string", f"English {form.replace('_', ' ')} form (use empty string if not applicable)"
        )

    schema = Schema(
        name="EnglishVerbConjugations",
        description="All conjugation forms for an English verb",
        properties={
            "forms": SchemaProperty(
                type="object",
                description="Dictionary of all verb conjugation forms",
                properties=form_properties,
            ),
            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            "notes": SchemaProperty(
                "string", "Notes about the conjugation pattern (e.g., irregular forms)"
            ),
        },
    )

    subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

    try:
        context = util.prompt_loader.get_context("wordfreq", "english_verb_conjugations")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "english_verb_conjugations")
        prompt = prompt_template.format(
            verb=verb, definition=definition, subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt, model=client.model, json_schema=schema, context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=verb,
                query_type="english_verb_conjugations",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.model,
            )
        except Exception as log_err:
            logger.error(f"Failed to log English conjugation query: {log_err}")

        # Validate and return response data
        if (
            response.structured_data
            and isinstance(response.structured_data, dict)
            and "forms" in response.structured_data
            and isinstance(response.structured_data["forms"], dict)
        ):
            forms = response.structured_data["forms"]
            return forms, True
        else:
            logger.warning(f"Invalid response format for English verb '{verb}'")
            return {}, False

    except Exception as e:
        logger.error(f"Error querying English conjugations for '{verb}': {type(e).__name__}: {e}")
        return {}, False
