#!/usr/bin/python3

"""Definition queries for linguistic analysis."""

import json
import logging
from typing import Dict, List, Any, Tuple

from clients.types import Schema, SchemaProperty
import util.prompt_loader
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.constants import VALID_POS_TYPES

logger = logging.getLogger(__name__)


def query_definitions(
    client,
    word: str,
    get_session_func
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Query LLM for definitions, POS, and lemma information.

    Args:
        client: UnifiedLLMClient instance
        word: Word to analyze
        get_session_func: Function to get database session

    Returns:
        Tuple of (list of definition data, success flag)
    """
    if not word or not isinstance(word, str):
        logger.error("Invalid word parameter provided")
        return [], False

    # Get valid grammatical forms for the schema
    valid_grammatical_forms = [form.value for form in GrammaticalForm]

    schema = Schema(
        name="WordDefinitions",
        description="Definitions and forms for a word",
        properties={
            "definitions": SchemaProperty(
                type="array",
                description="List of definitions and forms for the word",
                array_items_schema=Schema(
                    name="WordForm",
                    description="A single form/definition of the word",
                    properties={
                        "definition": SchemaProperty("string", "The definition of the word for this specific meaning"),
                        "pos": SchemaProperty("string", "The part of speech for this definition (noun, verb, etc.)", enum=list(VALID_POS_TYPES)),
                        "pos_subtype": SchemaProperty("string", "A subtype for the part of speech", enum=linguistic_db.get_all_pos_subtypes()),
                        "lemma": SchemaProperty("string", "The base form (lemma) for this definition"),
                        "grammatical_form": SchemaProperty("string", "The specific grammatical form (e.g., verb/infinitive, noun/plural)", enum=valid_grammatical_forms),
                        "is_base_form": SchemaProperty("boolean", "Whether this is the base form (infinitive, singular, etc.)"),
                        "phonetic_spelling": SchemaProperty("string", "Phonetic spelling of the word"),
                        "ipa_spelling": SchemaProperty("string", "International Phonetic Alphabet for the word"),
                        "special_case": SchemaProperty("boolean", "Whether this is a special case (foreign word, part of name, etc.)"),
                        "examples": SchemaProperty(
                            type="array",
                            description="Example sentences using this specific form",
                            items={"type": "string", "description": "Example sentence using this form"}
                        ),
                        "notes": SchemaProperty("string", "Additional notes about this form"),
                        "chinese_translation": SchemaProperty("string", "The Chinese translation of this form"),
                        "korean_translation": SchemaProperty("string", "The Korean translation of this form"),
                        "french_translation": SchemaProperty("string", "The French translation of this form"),
                        "swahili_translation": SchemaProperty("string", "The Swahili translation of this form"),
                        "vietnamese_translation": SchemaProperty("string", "The Vietnamese translation of this form"),
                        "lithuanian_translation": SchemaProperty("string", "The Lithuanian translation of this form"),
                        "confidence": SchemaProperty("number", "Confidence score from 0-1"),
                    }
                )
            )
        }
    )

    context = util.prompt_loader.get_context("wordfreq", "definitions")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "definitions")
    prompt = prompt_template.format(word=word)

    try:
        # Make a single API call without retries
        response = client.generate_chat(
            prompt=prompt,
            model=client.model,
            json_schema=schema,
            context=context
        )

        # Log successful query
        session = get_session_func()
        try:
            linguistic_db.log_query(
                session,
                word=word,
                query_type='definitions',
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.model
            )
        except Exception as log_err:
            logger.error(f"Failed to log successful query: {log_err}")

        # Validate and return response data
        if (response.structured_data and
            isinstance(response.structured_data, dict) and
            'definitions' in response.structured_data and
            isinstance(response.structured_data['definitions'], list)):
            return response.structured_data['definitions'], True
        else:
            logger.warning(f"Invalid response format for word '{word}'")
            return [], False

    except Exception as e:
        # More specific error logging
        logger.error(f"Error querying definitions for '{word}': {type(e).__name__}: {e}")
        return [], False
