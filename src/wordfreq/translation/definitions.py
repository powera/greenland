#!/usr/bin/python3

"""Definition queries for linguistic analysis."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage import database as linguistic_db
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_UNCOMMON,
    SENSE_PROMINENCE_VERY_COMMON,
)
from storage.utils.enums import get_subtype_values_for_pos
from wordfreq.translation.constants import VALID_POS_TYPES

logger = logging.getLogger(__name__)

# Language codes whose "<language>_translation" fields the definitions schema
# below requests. Callers that pick a translation field by language code should
# check against this so an unsupported language fails loudly instead of
# silently yielding no translation.
DEFINITIONS_PROMPT_LANGUAGES: Tuple[str, ...] = ("lt", "es", "es-419", "fr", "zh")

# How common a sense is, most to least. These are the values of
# Lemma.sense_prominence, so an answer can be stored directly on the lemma and
# feeds the frequency rollup in wordfreq.lexeme_frequency via
# SENSE_PROMINENCE_WEIGHTS. Senses are rated against the word's *other* senses,
# not on an absolute scale: judged absolutely, nearly every dictionary sense of a
# frequent word is "common" in modern English, which collapses the four tiers to
# two and leaves add_word's ceiling with nothing to rank by. A word may still
# have two "very_common" senses, or none -- this is a budget, not a forced
# ranking.
SENSE_PROMINENCE_ORDER: Tuple[str, ...] = (
    SENSE_PROMINENCE_VERY_COMMON,
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_UNCOMMON,
    SENSE_PROMINENCE_RARE,
)


def select_senses_to_add(
    definitions_list: List[Dict[str, Any]],
    max_senses: int = 4,
    min_senses: int = 2,
) -> List[Dict[str, Any]]:
    """
    Pick which of a word's senses are worth adding as lemmas.

    ``query_definitions`` returns every sense it can think of, including
    marginal ones -- "arrive" comes back with "reach a destination" and also
    "make a formal or public appearance". Adding all of them buries the common
    meaning; adding only the first loses real vocabulary.

    Senses are ordered by prominence and taken while they stay common enough:
    always the first ``min_senses``, then further senses only while they are
    ``common`` or better, up to ``max_senses``. So a word with four solid
    senses contributes four, and a word with one everyday sense plus three
    obscure ones contributes two.

    Args:
        definitions_list: Senses as returned by query_definitions
        max_senses: Never return more than this many
        min_senses: Return at least this many (if that many exist)

    Returns:
        The selected senses, most prominent first
    """
    if not definitions_list:
        return []

    rank = {value: index for index, value in enumerate(SENSE_PROMINENCE_ORDER)}
    default_rank = rank[SENSE_PROMINENCE_COMMON]

    ordered = sorted(
        definitions_list,
        key=lambda sense: rank.get(sense.get("sense_prominence", ""), default_rank),
    )

    # Senses at or above this prominence are worth adding beyond min_senses.
    keep_threshold = rank[SENSE_PROMINENCE_COMMON]

    selected: List[Dict[str, Any]] = []
    for sense in ordered[:max_senses]:
        prominence_rank = rank.get(sense.get("sense_prominence", ""), default_rank)
        if len(selected) < min_senses or prominence_rank <= keep_threshold:
            selected.append(sense)
        else:
            # Ordered by prominence, so nothing after this qualifies either.
            break

    return selected


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
                        "spanish_latam_translation": SchemaProperty(
                            "string",
                            "The neutral Latin American Spanish translation of this form",
                        ),
                        "french_translation": SchemaProperty(
                            "string", "The French translation of this form"
                        ),
                        "chinese_translation": SchemaProperty(
                            "string", "The Chinese translation of this form"
                        ),
                        "sense_prominence": SchemaProperty(
                            "string",
                            "How common this sense is relative to this word's other "
                            "senses. Reserve very_common for the one or two meanings a "
                            "learner meets first, and common for at most two or three "
                            "more; rate a sense uncommon or rare when it is specialized, "
                            "literary, archaic, or would not be worth teaching. Most "
                            "words should have at most three or four senses rated "
                            "common or better, however many senses are listed",
                            enum=list(SENSE_PROMINENCE_ORDER),
                        ),
                        "confidence": SchemaProperty("number", "Confidence score from 0-1"),
                    },
                ),
            )
        },
    )

    context_template = util.prompt_loader.get_context("translation", "definitions")
    context = context_template.format(
        noun_subtypes=", ".join(get_subtype_values_for_pos("noun")),
        verb_subtypes=", ".join(get_subtype_values_for_pos("verb")),
        adjective_subtypes=", ".join(get_subtype_values_for_pos("adjective")),
        adverb_subtypes=", ".join(get_subtype_values_for_pos("adverb")),
    )
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
