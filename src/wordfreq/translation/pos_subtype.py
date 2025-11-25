#!/usr/bin/python3

"""POS subtype classification for linguistic analysis."""

import json
import logging
import time
from typing import Dict, Any, Tuple

from clients.types import Schema, SchemaProperty
import util.prompt_loader
from wordfreq.storage import database as linguistic_db

logger = logging.getLogger(__name__)


def query_pos_subtype(
    client,
    word: str,
    definition_text: str,
    pos_type: str,
    get_session_func
) -> Tuple[str, bool]:
    """
    Query LLM for POS subtype for a definition.

    Args:
        client: UnifiedLLMClient instance
        word: The word to classify
        definition_text: The definition text
        pos_type: The part of speech (noun, verb, adjective, adverb)
        get_session_func: Function to get database session

    Returns:
        Tuple of (subtype string, success flag)
    """
    if not word or not isinstance(word, str) or not definition_text or not pos_type:
        logger.error("Invalid parameters provided for POS subtype query")
        return "other", False

    # Normalize pos_type to lowercase for consistency
    pos_type = pos_type.lower()
    valid_subtypes = linguistic_db.get_subtype_values_for_pos(pos_type)

    # Check if the POS is one we have subtypes for
    if pos_type not in ["noun", "verb", "adjective", "adverb"]:
        logger.warning(f"No subtypes defined for part of speech: {pos_type}")
        return "other", True

    schema = Schema(
        name="POSSubtype",
        description="Classification of a word into a specific part of speech subtype",
        properties={
            "classification": SchemaProperty(
                type="object",
                description="The classification result",
                properties={
                    "pos_subtype": SchemaProperty(
                        type="string",
                        description="The specific subtype within the part of speech category",
                        enum=valid_subtypes
                    ),
                    "confidence": SchemaProperty(
                        type="number",
                        description="Confidence score from 0-1"
                    ),
                    "reasoning": SchemaProperty(
                        type="string",
                        description="Explanation for the classification"
                    )
                }
            )
        }
    )

    # Select the appropriate context based on the part of speech
    context = util.prompt_loader.get_context("wordfreq", "pos_subtype", pos_type)
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "pos_subtype")
    prompt = prompt_template.format(word=word, pos_type=pos_type, definition_text=definition_text)

    try:
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
                query_type=f'pos_subtype_{pos_type}',
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.model
            )
        except Exception as log_err:
            logger.error(f"Failed to log successful subtype query: {log_err}")

        # Validate and return response data
        if (response.structured_data and
            isinstance(response.structured_data, dict) and
            "classification" in response.structured_data and
            "pos_subtype" in response.structured_data["classification"]):
            return response.structured_data["classification"]["pos_subtype"], True
        else:
            logger.warning(f"Invalid subtype response format for word '{word}'")
            return "other", False

    except Exception as e:
        # More specific error logging
        logger.error(f"Error querying POS subtype for '{word}': {type(e).__name__}: {e}")
        return "other", False


def update_missing_subtypes_for_word(
    client,
    word_text: str,
    get_session_func,
    throttle: float = 1.0
) -> Dict[str, Any]:
    """
    Add missing POS subtypes for all definitions of a word.

    Args:
        client: LinguisticClient instance
        word_text: Word to update subtypes for
        get_session_func: Function to get database session
        throttle: Time to wait between API calls (seconds)

    Returns:
        Dictionary with statistics about the processing
    """
    logger.info(f"Adding missing POS subtypes for definitions of '{word_text}'")

    session = get_session_func()
    word = linguistic_db.get_word_by_text(session, word_text)

    if not word:
        logger.warning(f"Word '{word_text}' not found in the database")
        return {
            "word": word_text,
            "total_definitions": 0,
            "missing_subtypes": 0,
            "processed": 0,
            "successful": 0
        }

    # Get all definitions for the word
    definitions = word.definitions
    total_definitions = len(definitions)

    if total_definitions == 0:
        logger.warning(f"No definitions found for word '{word_text}'")
        return {
            "word": word_text,
            "total_definitions": 0,
            "missing_subtypes": 0,
            "processed": 0,
            "successful": 0
        }

    # Filter for definitions without subtypes
    definitions_without_subtypes = [
        d for d in definitions
        if not d.pos_subtype or d.pos_subtype.strip() == ""
    ]

    missing_subtypes = len(definitions_without_subtypes)
    logger.info(f"Found {missing_subtypes} definitions without subtypes (out of {total_definitions} total)")

    successful = 0
    processed = 0

    for definition in definitions_without_subtypes:
        # Only process nouns, verbs, adjectives, and adverbs
        if definition.pos_type.lower() not in ["noun", "verb", "adjective", "adverb"]:
            logger.info(f"Skipping definition ID {definition.id} with POS '{definition.pos_type}'")
            continue

        subtype, success = query_pos_subtype(
            client,
            word.word,
            definition.definition_text,
            definition.pos_type,
            get_session_func
        )

        if success and subtype:
            # Update the definition with the subtype
            linguistic_db.update_definition(session, definition.id, pos_subtype=subtype)
            successful += 1
            logger.info(f"Added subtype '{subtype}' for definition ID {definition.id}")
        else:
            logger.warning(f"Failed to get subtype for definition ID {definition.id}")

        processed += 1

        # Throttle to avoid overloading the API
        time.sleep(throttle)

    logger.info(f"Processing complete for '{word_text}': {successful}/{processed} successful "
                f"({missing_subtypes} missing, {total_definitions} total)")

    return {
        "word": word_text,
        "total_definitions": total_definitions,
        "missing_subtypes": missing_subtypes,
        "processed": processed,
        "successful": successful
    }


def update_subtypes_for_batch(
    client,
    get_session_func,
    limit: int = 100,
    throttle: float = 1.0
) -> Dict[str, Any]:
    """
    Add missing POS subtypes for a batch of definitions.

    Args:
        client: LinguisticClient instance
        get_session_func: Function to get database session
        limit: Maximum number of definitions to process
        throttle: Time to wait between API calls (seconds)

    Returns:
        Dictionary with statistics about the processing
    """
    logger.info(f"Processing batch of {limit} definitions for POS subtypes")

    session = get_session_func()
    definitions = linguistic_db.get_definitions_without_subtypes(session, limit=limit)

    total = len(definitions)
    successful = 0
    processed = 0

    logger.info(f"Found {total} definitions without subtypes")

    for definition in definitions:
        # Only process nouns, verbs, adjectives, and adverbs
        if definition.pos_type.lower() not in ["noun", "verb", "adjective", "adverb"]:
            logger.info(f"Skipping definition ID {definition.id} with POS '{definition.pos_type}'")
            continue

        word = definition.word

        subtype, success = query_pos_subtype(
            client,
            word.word,
            definition.definition_text,
            definition.pos_type,
            get_session_func
        )

        if success and subtype:
            # Update the definition with the subtype
            linguistic_db.update_definition(session, definition.id, pos_subtype=subtype)
            successful += 1
            logger.info(f"Added subtype '{subtype}' for '{word.word}' definition ID {definition.id}")
        else:
            logger.warning(f"Failed to get subtype for '{word.word}' definition ID {definition.id}")

        processed += 1

        # Throttle to avoid overloading the API
        time.sleep(throttle)

    logger.info(f"Batch processing complete: {successful}/{processed} successful (out of {total} total)")

    return {
        "total": total,
        "processed": processed,
        "successful": successful
    }
