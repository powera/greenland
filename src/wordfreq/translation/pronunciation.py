#!/usr/bin/python3

"""Pronunciation queries for linguistic analysis."""

import json
import logging
import time
from typing import Dict, Any, Tuple, Optional

from clients.types import Schema, SchemaProperty
import util.prompt_loader
from wordfreq.storage import database as linguistic_db

logger = logging.getLogger(__name__)


def query_pronunciation(
    client, word: str, sentence: str, get_session_func
) -> Tuple[Dict[str, Any], bool]:
    """
    Query LLM for IPA and phonetic pronunciation of a word.

    Args:
        client: UnifiedLLMClient instance
        word: Word to get pronunciation for
        sentence: Context sentence showing usage of the word
        get_session_func: Function to get database session

    Returns:
        Tuple of (pronunciation data, success flag)
    """
    if not word or not isinstance(word, str) or not sentence or not isinstance(sentence, str):
        logger.error("Invalid parameters provided for pronunciation query")
        return {}, False

    schema = Schema(
        name="Pronunciation",
        description="Pronunciation information for a word",
        properties={
            "pronunciation": SchemaProperty(
                type="object",
                description="Pronunciation details",
                properties={
                    "ipa": SchemaProperty(
                        type="string",
                        description="IPA pronunciation for the word in American English",
                    ),
                    "phonetic": SchemaProperty(
                        type="string",
                        description="Simple phonetic pronunciation (e.g. 'SOO-duh-nim' for 'pseudonym')",
                    ),
                    "alternatives": SchemaProperty(
                        type="array",
                        description="Alternative valid pronunciations (British, Australian, etc.)",
                        array_items_schema=Schema(
                            name="AlternativePronunciation",
                            description="An alternative pronunciation variant",
                            properties={
                                "variant": SchemaProperty(
                                    type="string",
                                    description="Variant name (e.g. 'British', 'Australian', 'Alternative')",
                                ),
                                "ipa": SchemaProperty(
                                    type="string", description="IPA pronunciation for this variant"
                                ),
                            },
                        ),
                    ),
                    "confidence": SchemaProperty(
                        type="number", description="Confidence score from 0-1"
                    ),
                    "notes": SchemaProperty(
                        type="string", description="Additional notes about the pronunciation"
                    ),
                },
            )
        },
    )

    context = util.prompt_loader.get_context("wordfreq", "pronunciation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "pronunciation")
    prompt = prompt_template.format(word=word, sentence=sentence)

    try:
        response = client.generate_chat(
            prompt=prompt, model=client.model, json_schema=schema, context=context
        )

        # Log successful query
        session = get_session_func()
        try:
            linguistic_db.log_query(
                session,
                word=word,
                query_type="pronunciation",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=client.model,
            )
        except Exception as log_err:
            logger.error(f"Failed to log successful pronunciation query: {log_err}")

        # Validate and return response data
        if (
            response.structured_data
            and isinstance(response.structured_data, dict)
            and "pronunciation" in response.structured_data
            and isinstance(response.structured_data["pronunciation"], dict)
        ):
            return response.structured_data["pronunciation"], True
        else:
            logger.warning(f"Invalid pronunciation response format for word '{word}'")
            return {}, False

    except Exception as e:
        # More specific error logging
        logger.error(f"Error querying pronunciation for '{word}': {type(e).__name__}: {e}")
        return {}, False


def update_pronunciation_for_definition(
    client, definition_id: int, get_session_func, sentence: Optional[str] = None
) -> bool:
    """
    Update the pronunciation information for a specific definition.

    Args:
        client: UnifiedLLMClient instance
        definition_id: The ID of the definition to update
        get_session_func: Function to get database session
        sentence: Optional context sentence (if not provided, will use example or create one)

    Returns:
        Success flag
    """
    session = get_session_func()

    # Get the definition
    definition = (
        session.query(linguistic_db.Definition)
        .filter(linguistic_db.Definition.id == definition_id)
        .first()
    )
    if not definition:
        logger.warning(f"Definition with ID {definition_id} not found")
        return False

    # Get the word
    word = definition.word

    # Get a context sentence (from provided sentence, example, or generate a simple one)
    if not sentence:
        # Try to get an example sentence from the definition
        if definition.examples and len(definition.examples) > 0:
            sentence = definition.examples[0].example_text
        else:
            # This case should ideally not happen if definitions always have examples or a fallback
            # For now, we'll raise an error or log and return False
            logger.error(f"Could not get context sentence for definition ID {definition_id}")
            return False

    # Query for pronunciation
    pronunciation_data, success = query_pronunciation(client, word.word, sentence, get_session_func)

    if success:
        # Update the definition with the pronunciation information
        try:
            ipa = pronunciation_data.get("ipa", "")
            phonetic = pronunciation_data.get("phonetic", "")

            # Update the definition with the pronunciation
            linguistic_db.update_definition(
                session, definition.id, ipa_pronunciation=ipa, phonetic_pronunciation=phonetic
            )

            logger.info(f"Added pronunciations for '{word.word}' (definition ID: {definition.id})")
            logger.debug(f"IPA: {ipa}, Phonetic: {phonetic}")
            return True
        except Exception as e:
            logger.error(f"Error updating pronunciation for definition {definition_id}: {e}")
            return False
    else:
        logger.warning(
            f"Failed to get pronunciation for '{word.word}' (definition ID: {definition.id})"
        )
        return False


def update_missing_pronunciations_for_word(
    client, word_text: str, get_session_func, throttle: float = 1.0
) -> Dict[str, Any]:
    """
    Add missing pronunciations for all definitions of a word.

    Args:
        client: LinguisticClient instance
        word_text: Word to update pronunciations for
        get_session_func: Function to get database session
        throttle: Time to wait between API calls (seconds)

    Returns:
        Dictionary with statistics about the processing
    """
    logger.info(f"Adding missing pronunciations for definitions of '{word_text}'")

    session = get_session_func()
    word = linguistic_db.get_word_by_text(session, word_text)

    if not word:
        logger.warning(f"Word '{word_text}' not found in the database")
        return {
            "word": word_text,
            "total_definitions": 0,
            "missing_pronunciations": 0,
            "processed": 0,
            "successful": 0,
        }

    # Get all definitions for the word
    definitions = word.definitions
    total_definitions = len(definitions)

    if total_definitions == 0:
        logger.warning(f"No definitions found for word '{word_text}'")
        return {
            "word": word_text,
            "total_definitions": 0,
            "missing_pronunciations": 0,
            "processed": 0,
            "successful": 0,
        }

    # Filter for definitions without pronunciations
    definitions_without_pronunciations = [
        d for d in definitions if not d.ipa_pronunciation or not d.phonetic_pronunciation
    ]

    missing_pronunciations = len(definitions_without_pronunciations)
    logger.info(
        f"Found {missing_pronunciations} definitions without pronunciations (out of {total_definitions} total)"
    )

    successful = 0
    processed = 0

    for definition in definitions_without_pronunciations:
        success = update_pronunciation_for_definition(client, definition.id, get_session_func)
        processed += 1

        if success:
            successful += 1
            logger.info(f"Added pronunciation for definition ID {definition.id}")
        else:
            logger.warning(f"Failed to add pronunciation for definition ID {definition.id}")

        # Throttle to avoid overloading the API
        time.sleep(throttle)

    logger.info(
        f"Processing complete for '{word_text}': {successful}/{processed} successful "
        f"({missing_pronunciations} missing, {total_definitions} total)"
    )

    return {
        "word": word_text,
        "total_definitions": total_definitions,
        "missing_pronunciations": missing_pronunciations,
        "processed": processed,
        "successful": successful,
    }


def update_pronunciations_for_batch(
    client, get_session_func, limit: int = 100, throttle: float = 1.0
) -> Dict[str, Any]:
    """
    Add missing pronunciations for a batch of definitions.

    Args:
        client: LinguisticClient instance
        get_session_func: Function to get database session
        limit: Maximum number of definitions to process
        throttle: Time to wait between API calls (seconds)

    Returns:
        Dictionary with statistics about the processing
    """
    logger.info(f"Processing batch of {limit} definitions for pronunciations")

    session = get_session_func()
    definitions = linguistic_db.get_definitions_without_pronunciation(session, limit=limit)

    total = len(definitions)
    successful = 0
    processed = 0

    logger.info(f"Found {total} definitions without pronunciations")

    for definition in definitions:
        word = definition.word
        logger.info(f"Processing definition ID {definition.id} for word '{word.word}'")

        success = update_pronunciation_for_definition(client, definition.id, get_session_func)
        processed += 1

        if success:
            successful += 1
            logger.info(f"Added pronunciation for '{word.word}' definition ID {definition.id}")
        else:
            logger.warning(
                f"Failed to add pronunciation for '{word.word}' definition ID {definition.id}"
            )

        # Throttle to avoid overloading the API
        time.sleep(throttle)

    logger.info(
        f"Batch processing complete: {successful}/{processed} successful (out of {total} total)"
    )

    return {"total": total, "processed": processed, "successful": successful}
