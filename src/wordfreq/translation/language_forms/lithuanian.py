#!/usr/bin/python3

"""Lithuanian language form generation."""

import json
import logging
from typing import Dict, Tuple

from clients.types import Schema, SchemaProperty
from wordfreq.storage.models.enums import GrammaticalForm
import util.prompt_loader
from wordfreq.storage import database as linguistic_db

logger = logging.getLogger(__name__)

# Form mappings for Lithuanian
NOUN_FORM_MAPPING = {
    "nominative_singular": GrammaticalForm.NOUN_LT_NOMINATIVE_SINGULAR,
    "genitive_singular": GrammaticalForm.NOUN_LT_GENITIVE_SINGULAR,
    "dative_singular": GrammaticalForm.NOUN_LT_DATIVE_SINGULAR,
    "accusative_singular": GrammaticalForm.NOUN_LT_ACCUSATIVE_SINGULAR,
    "instrumental_singular": GrammaticalForm.NOUN_LT_INSTRUMENTAL_SINGULAR,
    "locative_singular": GrammaticalForm.NOUN_LT_LOCATIVE_SINGULAR,
    "vocative_singular": GrammaticalForm.NOUN_LT_VOCATIVE_SINGULAR,
    "nominative_plural": GrammaticalForm.NOUN_LT_NOMINATIVE_PLURAL,
    "genitive_plural": GrammaticalForm.NOUN_LT_GENITIVE_PLURAL,
    "dative_plural": GrammaticalForm.NOUN_LT_DATIVE_PLURAL,
    "accusative_plural": GrammaticalForm.NOUN_LT_ACCUSATIVE_PLURAL,
    "instrumental_plural": GrammaticalForm.NOUN_LT_INSTRUMENTAL_PLURAL,
    "locative_plural": GrammaticalForm.NOUN_LT_LOCATIVE_PLURAL,
    "vocative_plural": GrammaticalForm.NOUN_LT_VOCATIVE_PLURAL,
}

VERB_FORM_MAPPING = {
    "1s_pres": GrammaticalForm.VERB_LT_1S_PRES,
    "2s_pres": GrammaticalForm.VERB_LT_2S_PRES,
    "3s_m_pres": GrammaticalForm.VERB_LT_3S_M_PRES,
    "3s_f_pres": GrammaticalForm.VERB_LT_3S_F_PRES,
    "1p_pres": GrammaticalForm.VERB_LT_1P_PRES,
    "2p_pres": GrammaticalForm.VERB_LT_2P_PRES,
    "3p_m_pres": GrammaticalForm.VERB_LT_3P_M_PRES,
    "3p_f_pres": GrammaticalForm.VERB_LT_3P_F_PRES,
    "1s_past": GrammaticalForm.VERB_LT_1S_PAST,
    "2s_past": GrammaticalForm.VERB_LT_2S_PAST,
    "3s_m_past": GrammaticalForm.VERB_LT_3S_M_PAST,
    "3s_f_past": GrammaticalForm.VERB_LT_3S_F_PAST,
    "1p_past": GrammaticalForm.VERB_LT_1P_PAST,
    "2p_past": GrammaticalForm.VERB_LT_2P_PAST,
    "3p_m_past": GrammaticalForm.VERB_LT_3P_M_PAST,
    "3p_f_past": GrammaticalForm.VERB_LT_3P_F_PAST,
    "1s_fut": GrammaticalForm.VERB_LT_1S_FUT,
    "2s_fut": GrammaticalForm.VERB_LT_2S_FUT,
    "3s_m_fut": GrammaticalForm.VERB_LT_3S_M_FUT,
    "3s_f_fut": GrammaticalForm.VERB_LT_3S_F_FUT,
    "1p_fut": GrammaticalForm.VERB_LT_1P_FUT,
    "2p_fut": GrammaticalForm.VERB_LT_2P_FUT,
    "3p_m_fut": GrammaticalForm.VERB_LT_3P_M_FUT,
    "3p_f_fut": GrammaticalForm.VERB_LT_3P_F_FUT,
}

ADJECTIVE_FORM_MAPPING = {
    "nominative_singular_m": GrammaticalForm.ADJ_LT_NOMINATIVE_SINGULAR_M,
    "genitive_singular_m": GrammaticalForm.ADJ_LT_GENITIVE_SINGULAR_M,
    "dative_singular_m": GrammaticalForm.ADJ_LT_DATIVE_SINGULAR_M,
    "accusative_singular_m": GrammaticalForm.ADJ_LT_ACCUSATIVE_SINGULAR_M,
    "instrumental_singular_m": GrammaticalForm.ADJ_LT_INSTRUMENTAL_SINGULAR_M,
    "locative_singular_m": GrammaticalForm.ADJ_LT_LOCATIVE_SINGULAR_M,
    "vocative_singular_m": GrammaticalForm.ADJ_LT_VOCATIVE_SINGULAR_M,
    "nominative_singular_f": GrammaticalForm.ADJ_LT_NOMINATIVE_SINGULAR_F,
    "genitive_singular_f": GrammaticalForm.ADJ_LT_GENITIVE_SINGULAR_F,
    "dative_singular_f": GrammaticalForm.ADJ_LT_DATIVE_SINGULAR_F,
    "accusative_singular_f": GrammaticalForm.ADJ_LT_ACCUSATIVE_SINGULAR_F,
    "instrumental_singular_f": GrammaticalForm.ADJ_LT_INSTRUMENTAL_SINGULAR_F,
    "locative_singular_f": GrammaticalForm.ADJ_LT_LOCATIVE_SINGULAR_F,
    "vocative_singular_f": GrammaticalForm.ADJ_LT_VOCATIVE_SINGULAR_F,
    "nominative_plural_m": GrammaticalForm.ADJ_LT_NOMINATIVE_PLURAL_M,
    "genitive_plural_m": GrammaticalForm.ADJ_LT_GENITIVE_PLURAL_M,
    "dative_plural_m": GrammaticalForm.ADJ_LT_DATIVE_PLURAL_M,
    "accusative_plural_m": GrammaticalForm.ADJ_LT_ACCUSATIVE_PLURAL_M,
    "instrumental_plural_m": GrammaticalForm.ADJ_LT_INSTRUMENTAL_PLURAL_M,
    "locative_plural_m": GrammaticalForm.ADJ_LT_LOCATIVE_PLURAL_M,
    "vocative_plural_m": GrammaticalForm.ADJ_LT_VOCATIVE_PLURAL_M,
    "nominative_plural_f": GrammaticalForm.ADJ_LT_NOMINATIVE_PLURAL_F,
    "genitive_plural_f": GrammaticalForm.ADJ_LT_GENITIVE_PLURAL_F,
    "dative_plural_f": GrammaticalForm.ADJ_LT_DATIVE_PLURAL_F,
    "accusative_plural_f": GrammaticalForm.ADJ_LT_ACCUSATIVE_PLURAL_F,
    "instrumental_plural_f": GrammaticalForm.ADJ_LT_INSTRUMENTAL_PLURAL_F,
    "locative_plural_f": GrammaticalForm.ADJ_LT_LOCATIVE_PLURAL_F,
    "vocative_plural_f": GrammaticalForm.ADJ_LT_VOCATIVE_PLURAL_F,
}


def query_lithuanian_noun_declensions(
    client,
    lemma_id: int,
    get_session_func
) -> Tuple[Dict[str, str], bool, str]:
    """
    Query LLM for all Lithuanian noun declensions (7 cases × 2 numbers).

    Args:
        client: UnifiedLLMClient instance
        lemma_id: The ID of the lemma to generate declensions for
        get_session_func: Function to get database session

    Returns:
        Tuple of (dict mapping form names to declensions, success flag, number_type)
        where number_type is one of: 'regular', 'plurale_tantum', 'singulare_tantum'
    """
    session = get_session_func()

    # Get the lemma
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma:
        logger.error(f"Lemma with ID {lemma_id} not found")
        return {}, False, 'regular'

    if not lemma.lithuanian_translation:
        logger.error(f"Lemma ID {lemma_id} has no Lithuanian translation")
        return {}, False, 'regular'

    if lemma.pos_type.lower() != 'noun':
        logger.error(f"Lemma ID {lemma_id} is not a noun (pos_type: {lemma.pos_type})")
        return {}, False, 'regular'

    noun = lemma.lithuanian_translation
    english_word = lemma.lemma_text
    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # All 14 forms (7 cases × 2 numbers)
    singular_fields = [
        "nominative_singular", "genitive_singular", "dative_singular", "accusative_singular",
        "instrumental_singular", "locative_singular", "vocative_singular"
    ]
    plural_fields = [
        "nominative_plural", "genitive_plural", "dative_plural", "accusative_plural",
        "instrumental_plural", "locative_plural", "vocative_plural"
    ]

    # Build schema properties for all forms
    form_properties = {}
    for form in singular_fields + plural_fields:
        form_properties[form] = SchemaProperty(
            "string",
            f"Lithuanian {form.replace('_', ' ')} (use empty string if not applicable)"
        )

    schema = Schema(
        name="LithuanianNounDeclensions",
        description="All declension forms for a Lithuanian noun",
        properties={
            "number_type": SchemaProperty(
                "string",
                "The number type of this noun",
                enum=["regular", "plurale_tantum", "singulare_tantum"]
            ),
            "forms": SchemaProperty(
                type="object",
                description="Dictionary of all noun declension forms. Use empty string for forms that don't exist (e.g., singular forms for plurale tantum)",
                properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            "notes": SchemaProperty("string", "Notes about the declension pattern")
        }
    )

    subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

    try:
        context = util.prompt_loader.get_context("wordfreq", "lithuanian_noun_declensions")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "lithuanian_noun_declensions")
        prompt = prompt_template.format(
            noun=noun,
            english_word=english_word,
            definition=definition,
            subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt,
            model=client.model,
            json_schema=schema,
            context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=noun,
                query_type='lithuanian_noun_declensions',
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.model
            )
        except Exception as log_err:
            logger.error(f"Failed to log Lithuanian declension query: {log_err}")

        # Validate and return response data
        if (response.structured_data and
            isinstance(response.structured_data, dict) and
            'forms' in response.structured_data and
            isinstance(response.structured_data['forms'], dict)):
            # Filter out forms based on number_type
            forms = response.structured_data['forms']
            number_type = response.structured_data.get('number_type', 'regular')

            # For plurale_tantum, remove all singular forms
            if number_type == 'plurale_tantum':
                forms = {k: v for k, v in forms.items() if not k.endswith('_singular')}
                logger.info(f"Filtered singular forms for plurale_tantum noun '{noun}'")
            # For singulare_tantum, remove all plural forms
            elif number_type == 'singulare_tantum':
                forms = {k: v for k, v in forms.items() if not k.endswith('_plural')}
                logger.info(f"Filtered plural forms for singulare_tantum noun '{noun}'")

            return forms, True, number_type
        else:
            logger.warning(f"Invalid response format for Lithuanian noun '{noun}'")
            return {}, False, 'regular'

    except Exception as e:
        logger.error(f"Error querying Lithuanian declensions for '{noun}': {type(e).__name__}: {e}")
        return {}, False, 'regular'


def query_lithuanian_verb_conjugations(
    client,
    lemma_id: int,
    get_session_func
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM for all Lithuanian verb conjugations (3 tenses × 8 persons).

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

    if not lemma.lithuanian_translation:
        logger.error(f"Lemma ID {lemma_id} has no Lithuanian translation")
        return {}, False

    if lemma.pos_type.lower() != 'verb':
        logger.error(f"Lemma ID {lemma_id} is not a verb (pos_type: {lemma.pos_type})")
        return {}, False

    verb = lemma.lithuanian_translation
    english_verb = lemma.lemma_text
    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # All 24 forms (3 tenses × 8 persons with gender distinction)
    present_fields = [
        "1s_pres", "2s_pres", "3s_m_pres", "3s_f_pres",
        "1p_pres", "2p_pres", "3p_m_pres", "3p_f_pres"
    ]
    past_fields = [
        "1s_past", "2s_past", "3s_m_past", "3s_f_past",
        "1p_past", "2p_past", "3p_m_past", "3p_f_past"
    ]
    future_fields = [
        "1s_fut", "2s_fut", "3s_m_fut", "3s_f_fut",
        "1p_fut", "2p_fut", "3p_m_fut", "3p_f_fut"
    ]

    # Build schema properties for all forms
    form_properties = {}
    for form in present_fields + past_fields + future_fields:
        form_properties[form] = SchemaProperty(
            "string",
            f"Lithuanian {form.replace('_', ' ')} form (use empty string if not applicable)"
        )

    schema = Schema(
        name="LithuanianVerbConjugations",
        description="All conjugation forms for a Lithuanian verb",
        properties={
            "forms": SchemaProperty(
                type="object",
                description="Dictionary of all verb conjugation forms",
                properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            "notes": SchemaProperty("string", "Notes about the conjugation pattern")
        }
    )

    subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

    try:
        context = util.prompt_loader.get_context("wordfreq", "lithuanian_verb_conjugations")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "lithuanian_verb_conjugations")
        prompt = prompt_template.format(
            verb=verb,
            english_verb=english_verb,
            definition=definition,
            subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt,
            model=client.model,
            json_schema=schema,
            context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=verb,
                query_type='lithuanian_verb_conjugations',
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.model
            )
        except Exception as log_err:
            logger.error(f"Failed to log Lithuanian conjugation query: {log_err}")

        # Validate and return response data
        if (response.structured_data and
            isinstance(response.structured_data, dict) and
            'forms' in response.structured_data and
            isinstance(response.structured_data['forms'], dict)):
            forms = response.structured_data['forms']
            return forms, True
        else:
            logger.warning(f"Invalid response format for Lithuanian verb '{verb}'")
            return {}, False

    except Exception as e:
        logger.error(f"Error querying Lithuanian conjugations for '{verb}': {type(e).__name__}: {e}")
        return {}, False


def query_lithuanian_adjective_declensions(
    client,
    lemma_id: int,
    get_session_func
) -> Tuple[Dict[str, str], bool]:
    """
    Query LLM for all Lithuanian adjective declensions (7 cases × 2 numbers × 2 genders = 28 forms).

    Args:
        client: UnifiedLLMClient instance
        lemma_id: The ID of the lemma to generate declensions for
        get_session_func: Function to get database session

    Returns:
        Tuple of (dict mapping form names to declensions, success flag)
    """
    session = get_session_func()

    # Get the lemma
    lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
    if not lemma:
        logger.error(f"Lemma with ID {lemma_id} not found")
        return {}, False

    if not lemma.lithuanian_translation:
        logger.error(f"Lemma ID {lemma_id} has no Lithuanian translation")
        return {}, False

    if lemma.pos_type.lower() != 'adjective':
        logger.error(f"Lemma ID {lemma_id} is not an adjective (pos_type: {lemma.pos_type})")
        return {}, False

    adjective = lemma.lithuanian_translation
    english_adjective = lemma.lemma_text
    definition = lemma.definition_text
    pos_subtype = lemma.pos_subtype

    # All 28 forms (7 cases × 2 numbers × 2 genders)
    masculine_singular_fields = [
        "nominative_singular_m", "genitive_singular_m", "dative_singular_m", "accusative_singular_m",
        "instrumental_singular_m", "locative_singular_m", "vocative_singular_m"
    ]
    feminine_singular_fields = [
        "nominative_singular_f", "genitive_singular_f", "dative_singular_f", "accusative_singular_f",
        "instrumental_singular_f", "locative_singular_f", "vocative_singular_f"
    ]
    masculine_plural_fields = [
        "nominative_plural_m", "genitive_plural_m", "dative_plural_m", "accusative_plural_m",
        "instrumental_plural_m", "locative_plural_m", "vocative_plural_m"
    ]
    feminine_plural_fields = [
        "nominative_plural_f", "genitive_plural_f", "dative_plural_f", "accusative_plural_f",
        "instrumental_plural_f", "locative_plural_f", "vocative_plural_f"
    ]

    # Build schema properties for all forms
    form_properties = {}
    for form in masculine_singular_fields + feminine_singular_fields + masculine_plural_fields + feminine_plural_fields:
        form_properties[form] = SchemaProperty(
            "string",
            f"Lithuanian {form.replace('_', ' ')} (use empty string if not applicable)"
        )

    schema = Schema(
        name="LithuanianAdjectiveDeclensions",
        description="All declension forms for a Lithuanian adjective",
        properties={
            "forms": SchemaProperty(
                type="object",
                description="Dictionary of all adjective declension forms",
                properties=form_properties
            ),
            "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            "notes": SchemaProperty("string", "Notes about the declension pattern")
        }
    )

    subtype_context = f" (category: {pos_subtype})" if pos_subtype else ""

    try:
        context = util.prompt_loader.get_context("wordfreq", "lithuanian_adjective_declensions")
        prompt_template = util.prompt_loader.get_prompt("wordfreq", "lithuanian_adjective_declensions")
        prompt = prompt_template.format(
            adjective=adjective,
            english_adjective=english_adjective,
            definition=definition,
            subtype_context=subtype_context
        )

        response = client.generate_chat(
            prompt=prompt,
            model=client.model,
            json_schema=schema,
            context=context
        )

        # Log successful query
        try:
            linguistic_db.log_query(
                session,
                word=adjective,
                query_type='lithuanian_adjective_declensions',
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.model
            )
        except Exception as log_err:
            logger.error(f"Failed to log Lithuanian adjective declension query: {log_err}")

        # Validate and return response data
        if (response.structured_data and
            isinstance(response.structured_data, dict) and
            'forms' in response.structured_data and
            isinstance(response.structured_data['forms'], dict)):
            forms = response.structured_data['forms']
            return forms, True
        else:
            logger.warning(f"Invalid response format for Lithuanian adjective '{adjective}'")
            return {}, False

    except Exception as e:
        logger.error(f"Error querying Lithuanian adjective declensions for '{adjective}': {type(e).__name__}: {e}")
        return {}, False
