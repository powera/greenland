#!/usr/bin/python3

"""English language form generation."""

import json
import logging
from typing import Dict, Tuple

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.models.enums import GrammaticalForm

logger = logging.getLogger(__name__)

# Form mapping for English nouns
NOUN_FORM_MAPPING = {
    "singular": GrammaticalForm.NOUN_EN_SINGULAR,
    "plural": GrammaticalForm.NOUN_EN_PLURAL,
}

# Form mapping for English adjectives
ADJECTIVE_FORM_MAPPING = {
    "positive": GrammaticalForm.ADJ_EN_POSITIVE,
    "comparative": GrammaticalForm.ADJ_EN_COMPARATIVE,
    "superlative": GrammaticalForm.ADJ_EN_SUPERLATIVE,
}

# Form mapping for English adverbs
ADVERB_FORM_MAPPING = {
    "positive": GrammaticalForm.ADVERB_EN_POSITIVE,
    "comparative": GrammaticalForm.ADVERB_EN_COMPARATIVE,
    "superlative": GrammaticalForm.ADVERB_EN_SUPERLATIVE,
}

# Form mapping for English verbs
VERB_FORM_MAPPING = {
    "1s_present": GrammaticalForm.VERB_EN_1S_PRESENT,
    "2s_present": GrammaticalForm.VERB_EN_2S_PRESENT,
    "3s_present": GrammaticalForm.VERB_EN_3S_PRESENT,
    "1p_present": GrammaticalForm.VERB_EN_1P_PRESENT,
    "2p_present": GrammaticalForm.VERB_EN_2P_PRESENT,
    "3p_present": GrammaticalForm.VERB_EN_3P_PRESENT,
    "1s_past": GrammaticalForm.VERB_EN_1S_PAST,
    "2s_past": GrammaticalForm.VERB_EN_2S_PAST,
    "3s_past": GrammaticalForm.VERB_EN_3S_PAST,
    "1p_past": GrammaticalForm.VERB_EN_1P_PAST,
    "2p_past": GrammaticalForm.VERB_EN_2P_PAST,
    "3p_past": GrammaticalForm.VERB_EN_3P_PAST,
    "1s_future": GrammaticalForm.VERB_EN_1S_FUTURE,
    "2s_future": GrammaticalForm.VERB_EN_2S_FUTURE,
    "3s_future": GrammaticalForm.VERB_EN_3S_FUTURE,
    "1p_future": GrammaticalForm.VERB_EN_1P_FUTURE,
    "2p_future": GrammaticalForm.VERB_EN_2P_FUTURE,
    "3p_future": GrammaticalForm.VERB_EN_3P_FUTURE,
    "2s_imp": GrammaticalForm.VERB_EN_2S_IMP,
    "2p_imp": GrammaticalForm.VERB_EN_2P_IMP,
}


def query_english_verb_conjugations(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM for all English verb conjugations (6 persons × 3 tenses + 2 imperatives = 20 forms).

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

    # All 20 forms (6 persons × 3 tenses + 2 imperatives)
    present_fields = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    past_fields = ["1s_past", "2s_past", "3s_past", "1p_past", "2p_past", "3p_past"]
    future_fields = ["1s_future", "2s_future", "3s_future", "1p_future", "2p_future", "3p_future"]
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
        context = util.prompt_loader.get_context("language_forms", "english/verb")
        prompt_template = util.prompt_loader.get_prompt("language_forms", "english/verb")
        prompt = prompt_template.format(
            verb=verb, definition=definition, subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt, model=client.default_model, json_schema=schema, context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=verb,
                query_type="english_verb_conjugations",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.default_model,
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


def query_english_noun_forms(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM for English noun forms (singular and plural).

    Args:
        client: UnifiedLLMClient instance
        lemma_id: The ID of the lemma to generate noun forms for
        get_session_func: Function to get database session

    Returns:
        Tuple of (dict mapping form names to noun forms, success flag)
    """
    session = get_session_func()

    # Get the lemma
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma:
        logger.error(f"Lemma with ID {lemma_id} not found")
        return {}, False

    if lemma.pos_type.lower() != "noun":
        logger.error(f"Lemma ID {lemma_id} is not a noun (pos_type: {lemma.pos_type})")
        return {}, False

    noun = lemma.lemma_text
    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # Both singular and plural forms
    fields = ["singular", "plural"]

    # Build schema properties
    form_properties = {}
    for form in fields:
        form_properties[form] = SchemaProperty(
            "string", f"English {form} form (use empty string if not applicable)"
        )

    schema = Schema(
        name="EnglishNounForms",
        description="Singular and plural forms for an English noun",
        properties={
            "forms": SchemaProperty(
                type="object",
                description="Dictionary of noun forms",
                properties=form_properties,
            ),
            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            "notes": SchemaProperty(
                "string", "Notes about the noun pattern (e.g., irregular plural, mass noun)"
            ),
        },
    )

    subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

    try:
        context = util.prompt_loader.get_context("language_forms", "english/noun")
        prompt_template = util.prompt_loader.get_prompt("language_forms", "english/noun")
        prompt = prompt_template.format(
            noun=noun, definition=definition, subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt, model=client.default_model, json_schema=schema, context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=noun,
                query_type="english_noun_forms",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.default_model,
            )
        except Exception as log_err:
            logger.error(f"Failed to log English noun query: {log_err}")

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
            logger.warning(f"Invalid response format for English noun '{noun}'")
            return {}, False

    except Exception as e:
        logger.error(f"Error querying English noun forms for '{noun}': {type(e).__name__}: {e}")
        return {}, False


def query_english_adjective_forms(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM for English adjective forms (positive, comparative, superlative).

    Args:
        client: UnifiedLLMClient instance
        lemma_id: The ID of the lemma to generate adjective forms for
        get_session_func: Function to get database session

    Returns:
        Tuple of (dict mapping form names to adjective forms, success flag)
    """
    session = get_session_func()

    # Get the lemma
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma:
        logger.error(f"Lemma with ID {lemma_id} not found")
        return {}, False

    if lemma.pos_type.lower() != "adjective":
        logger.error(f"Lemma ID {lemma_id} is not an adjective (pos_type: {lemma.pos_type})")
        return {}, False

    adjective = lemma.lemma_text
    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # All 3 comparative forms
    fields = ["positive", "comparative", "superlative"]

    # Build schema properties
    form_properties = {}
    for form in fields:
        form_properties[form] = SchemaProperty(
            "string", f"English {form} form (use empty string if not applicable)"
        )

    schema = Schema(
        name="EnglishAdjectiveForms",
        description="Comparative forms for an English adjective",
        properties={
            "forms": SchemaProperty(
                type="object",
                description="Dictionary of adjective forms",
                properties=form_properties,
            ),
            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            "notes": SchemaProperty(
                "string", "Notes about the pattern (e.g., irregular, absolute adjective)"
            ),
        },
    )

    subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

    try:
        context = util.prompt_loader.get_context("language_forms", "english/adjective")
        prompt_template = util.prompt_loader.get_prompt("language_forms", "english/adjective")
        prompt = prompt_template.format(
            adjective=adjective, definition=definition, subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt, model=client.default_model, json_schema=schema, context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=adjective,
                query_type="english_adjective_forms",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.default_model,
            )
        except Exception as log_err:
            logger.error(f"Failed to log English adjective query: {log_err}")

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
            logger.warning(f"Invalid response format for English adjective '{adjective}'")
            return {}, False

    except Exception as e:
        logger.error(
            f"Error querying English adjective forms for '{adjective}': {type(e).__name__}: {e}"
        )
        return {}, False


def query_english_adverb_forms(
    client, lemma_id: int, get_session_func
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM for English adverb forms (positive, comparative, superlative).

    Args:
        client: UnifiedLLMClient instance
        lemma_id: The ID of the lemma to generate adverb forms for
        get_session_func: Function to get database session

    Returns:
        Tuple of (dict mapping form names to adverb forms, success flag)
    """
    session = get_session_func()

    # Get the lemma
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma:
        logger.error(f"Lemma with ID {lemma_id} not found")
        return {}, False

    if lemma.pos_type.lower() != "adverb":
        logger.error(f"Lemma ID {lemma_id} is not an adverb (pos_type: {lemma.pos_type})")
        return {}, False

    adverb = lemma.lemma_text
    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # All 3 comparative forms
    fields = ["positive", "comparative", "superlative"]

    # Build schema properties
    form_properties = {}
    for form in fields:
        form_properties[form] = SchemaProperty(
            "string", f"English {form} form (use empty string if not applicable)"
        )

    schema = Schema(
        name="EnglishAdverbForms",
        description="Comparative forms for an English adverb",
        properties={
            "forms": SchemaProperty(
                type="object",
                description="Dictionary of adverb forms",
                properties=form_properties,
            ),
            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            "notes": SchemaProperty(
                "string", "Notes about the pattern (e.g., irregular, no comparative forms)"
            ),
        },
    )

    subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

    try:
        context = util.prompt_loader.get_context("language_forms", "english/adverb")
        prompt_template = util.prompt_loader.get_prompt("language_forms", "english/adverb")
        prompt = prompt_template.format(
            adverb=adverb, definition=definition, subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt, model=client.default_model, json_schema=schema, context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=adverb,
                query_type="english_adverb_forms",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.default_model,
            )
        except Exception as log_err:
            logger.error(f"Failed to log English adverb query: {log_err}")

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
            logger.warning(f"Invalid response format for English adverb '{adverb}'")
            return {}, False

    except Exception as e:
        logger.error(f"Error querying English adverb forms for '{adverb}': {type(e).__name__}: {e}")
        return {}, False
