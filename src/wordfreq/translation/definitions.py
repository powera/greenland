#!/usr/bin/python3

"""Definition queries for linguistic analysis."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage import database as linguistic_db
from wordfreq.translation.constants import VALID_POS_TYPES

logger = logging.getLogger(__name__)

# Language codes whose "<language>_translation" fields the definitions schema
# below requests. Callers that pick a translation field by language code should
# check against this so an unsupported language fails loudly instead of
# silently yielding no translation.
DEFINITIONS_PROMPT_LANGUAGES: Tuple[str, ...] = ("lt", "es", "fr", "zh")

# How common a sense is, most to least. A word's senses are rated
# independently, so "arrive" can have two "most_common" senses; this is a
# judgement about the sense, not a ranking within the response.
SENSE_FREQUENCIES: Tuple[str, ...] = (
    "most_common",
    "somewhat_common",
    "uncommon",
    "rare",
    "very_rare",
)


def query_definitions(
    client: Any,
    word: str,
    get_session_func: Callable,
    model: Optional[str] = None,
    example_sentence: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Query LLM for definitions, POS, and lemma information.

    Args:
        client: UnifiedLLMClient instance
        model: Model name to use (optional, uses client.model if available)
        word: Word to analyze
        get_session_func: Function to get database session

    Returns:
        Tuple of (list of definition data, success flag)
    """
    if not word or not isinstance(word, str):
        logger.error("Invalid word parameter provided")
        return [], False

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
                        "definition": SchemaProperty(
                            "string", "The definition of the word for this specific meaning"
                        ),
                        "pos": SchemaProperty(
                            "string",
                            "The part of speech for this definition (noun, verb, etc.)",
                            enum=list(VALID_POS_TYPES),
                        ),
                        "pos_subtype": SchemaProperty(
                            "string",
                            "A subtype for the part of speech",
                            enum=linguistic_db.get_all_pos_subtypes(),
                        ),
                        "lemma": SchemaProperty(
                            "string", "The base form (lemma) for this definition"
                        ),
                        # No grammatical_form property: this prompt analyses one
                        # English word per definition and process_word records a
                        # single form, so the form follows from pos_type and is
                        # derived by determine_default_grammatical_form. Listing
                        # the enum here meant sending all 1238 GrammaticalForm
                        # values -- every language's full conjugation tables,
                        # ~28.5k characters, roughly two thirds of the prompt --
                        # to ask about one English word.
                        "is_base_form": SchemaProperty(
                            "boolean", "Whether this is the base form (infinitive, singular, etc.)"
                        ),
                        "phonetic_spelling": SchemaProperty(
                            "string", "Phonetic spelling of the word"
                        ),
                        "ipa_spelling": SchemaProperty(
                            "string", "International Phonetic Alphabet for the word"
                        ),
                        "special_case": SchemaProperty(
                            "boolean",
                            "Whether this is a special case (foreign word, part of name, etc.)",
                        ),
                        "examples": SchemaProperty(
                            type="array",
                            description="Example sentences using this specific form",
                            items={
                                "type": "string",
                                "description": "Example sentence using this form",
                            },
                        ),
                        "notes": SchemaProperty("string", "Additional notes about this form"),
                        # Translations are limited to the current target
                        # languages (lt/es/fr/zh). The prompt previously asked
                        # for Korean, Swahili and Vietnamese as well; those
                        # dated to an older target set, were never stored, and
                        # only inflated the prompt. Callers that build a field
                        # name as f"{language}_translation" (dramblys
                        # --target-language, client.get_translation_for_form)
                        # can only request one of these four.
                        "lithuanian_translation": SchemaProperty(
                            "string", "The Lithuanian translation of this form"
                        ),
                        "spanish_translation": SchemaProperty(
                            "string", "The Spanish translation of this form"
                        ),
                        "french_translation": SchemaProperty(
                            "string", "The French translation of this form"
                        ),
                        "chinese_translation": SchemaProperty(
                            "string", "The Chinese translation of this form"
                        ),
                        "sense_frequency": SchemaProperty(
                            "string",
                            "How common this sense is for this word in general "
                            "modern English, independent of the other senses",
                            enum=list(SENSE_FREQUENCIES),
                        ),
                        "confidence": SchemaProperty("number", "Confidence score from 0-1"),
                    },
                ),
            )
        },
    )

    context = util.prompt_loader.get_context("translation", "definitions")
    prompt_template = util.prompt_loader.get_prompt("translation", "definitions")
    prompt = prompt_template.format(word=word)
    if example_sentence:
        prompt += f'\n\nContext: this word appears in the sentence: "{example_sentence}"'

    # Get model name from parameter or client attribute
    model_name: str = cast(str, model or getattr(client, "model", "gpt-5.4-mini"))

    try:
        # Make a single API call without retries
        response = client.generate_chat(
            prompt=prompt, model=model_name, json_schema=schema, context=context
        )

        # Log successful query
        session = get_session_func()
        try:
            linguistic_db.log_query(
                session,
                word=word,
                query_type="definitions",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=model_name,
            )
        except Exception as log_err:
            logger.error(f"Failed to log successful query: {log_err}")

        # Validate and return response data
        if (
            response.structured_data
            and isinstance(response.structured_data, dict)
            and "definitions" in response.structured_data
            and isinstance(response.structured_data["definitions"], list)
        ):
            return response.structured_data["definitions"], True
        else:
            logger.warning(f"Invalid response format for word '{word}'")
            return [], False

    except Exception as e:
        # More specific error logging
        logger.error(f"Error querying definitions for '{word}': {type(e).__name__}: {e}")
        return [], False
