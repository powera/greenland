#!/usr/bin/python3

"""Definition queries for linguistic analysis."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import constants
import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage import database as linguistic_db
from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_UNCOMMON,
    SENSE_PROMINENCE_VERY_COMMON,
)
from storage.models.guid_prefixes import render_subtype_list
from storage.utils.enums import get_subtype_values_for_pos
from words.linguistic_constants import MAJOR_POS_TYPES, VALID_POS_TYPES

logger = logging.getLogger(__name__)

# Parts of speech with a real choice of subtype, which build_subtype_prompt's
# call makes.  numeral has no catch-all, only cardinal and ordinal; every other
# closed class has "<pos>_other" as its only subtype and needs no call.
SUBTYPED_POS_TYPES = frozenset({*MAJOR_POS_TYPES, "numeral"})

# The open-class catch-all as the subtype enums and lists spell it; add_word's
# _normalize_subtype turns it into "<pos>_other".
_CATCH_ALL_SUBTYPE = "other"

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
    pos_type: Optional[str] = None,
    ask_subtype: bool = True,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Query LLM for definitions, POS, and lemma information.

    Args:
        client: UnifiedLLMClient instance
        model: Model name to use (optional, uses client.model if available)
        word: Word to analyze
        get_session_func: Function to get database session
        pos_type: Ask only for the senses of this part of speech ("verb" for
            "place", whose noun is already stored). A request, not a filter:
            callers that need one POS must still drop what else comes back.
        ask_subtype: Also ask for each sense's ``pos_subtype``. This call can
            only list every part of speech's subtypes as bare names, and from
            the names alone the model often picks the wrong one or the
            catch-all. With False the senses come back without a subtype, and
            the caller asks for it per sense with :func:`query_sense_subtype`.

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
                            "string", "The meaning of the lemma in this sense"
                        ),
                        "pos": SchemaProperty(
                            "string",
                            "The part of speech for this definition (noun, verb, etc.)",
                            enum=list(VALID_POS_TYPES),
                        ),
                        # Without ask_subtype the caller asks per sense
                        # afterwards (query_sense_subtype), where one POS's
                        # subtypes can be shown with their descriptions.
                        **(
                            {
                                "pos_subtype": SchemaProperty(
                                    "string",
                                    "A subtype for the part of speech",
                                    enum=linguistic_db.get_all_pos_subtypes(),
                                )
                            }
                            if ask_subtype
                            else {}
                        ),
                        "lemma": SchemaProperty(
                            "string", "The base form (lemma) for this definition"
                        ),
                        # No grammatical_form property: this prompt analyses one
                        # English word per definition and add_word records a
                        # single form, so the form follows from pos_type and is
                        # derived by determine_default_grammatical_form. Listing
                        # the enum here meant sending all 1238 GrammaticalForm
                        # values -- every language's full conjugation tables,
                        # ~28.5k characters, roughly two thirds of the prompt --
                        # to ask about one English word.
                        "is_base_form": SchemaProperty(
                            "boolean",
                            "Whether the given word is the base form (infinitive, singular, "
                            "etc.) of this sense's lemma",
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
                        # The standard English term naming this sense, which is
                        # not always the queried token: "gas" is a colloquial
                        # clipping of both "gasoline" and "natural gas", and the
                        # sense deserves the full term as its headword. Distinct
                        # from "lemma", which is the queried token's uninflected
                        # form ("done" -> "do") and drives grammatical-form
                        # selection; conflating the two would make a clipping
                        # look like an inflection.
                        "english_translation": SchemaProperty(
                            "string", "The standard English term for this sense"
                        ),
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

    if ask_subtype:
        context = util.prompt_loader.get_context("translation", "definitions").format(
            noun_subtypes=", ".join(get_subtype_values_for_pos("noun")),
            verb_subtypes=", ".join(get_subtype_values_for_pos("verb")),
            adjective_subtypes=", ".join(get_subtype_values_for_pos("adjective")),
            adverb_subtypes=", ".join(get_subtype_values_for_pos("adverb")),
        )
        prompt_template = util.prompt_loader.get_prompt("translation", "definitions")
    else:
        # The same prompt with the subtype lists left out.
        context = util.prompt_loader.get_context("translation", "definitions_senses")
        prompt_template = util.prompt_loader.get_prompt("translation", "definitions_senses")
    prompt = prompt_template.format(word=word)
    if pos_type:
        prompt += f"\n\nList only the senses in which '{word}' is used as a {pos_type}."
    if example_sentence:
        prompt += f'\n\nContext: this word appears in the sentence: "{example_sentence}"'

    # Get model name from parameter or client attribute
    model_name: str = cast(str, model or getattr(client, "model", constants.DEFAULT_MODEL))

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


def build_subtype_prompt(
    word: str,
    definition: str,
    pos_type: str,
    *,
    domain: Optional[str] = None,
    include_catch_all: bool = True,
) -> Tuple[str, str, Schema]:
    """Build the context, prompt and schema for one sense's subtype-only call.

    It shows only ``pos_type``'s subtypes, each with its description and
    examples.  Asked in the senses call, every part of speech's subtypes had
    to be listed, and as bare names: well over a hundred glosses would be too
    much for one call, and from the names alone the model filed referee as a
    participant_role and gave volley the catch-all.

    Args:
        word: The English word or term.
        definition: The definition of the sense being classified.
        pos_type: Its part of speech; one of :data:`SUBTYPED_POS_TYPES`.
        domain: The field a specialized term belongs to ("chess"), for
            add_sense.  Without it the prompt is for general vocabulary.
        include_catch_all: Offer the ``other`` catch-all.  add_word offers it
            and queues a sense that takes it for review; add_sense withholds
            it, since a domain term always has a real subtype.
    """
    prompt_type = "sense_subtype" if domain is not None else "definitions_subtype"
    context = util.prompt_loader.get_context("translation", prompt_type).format(
        pos_type=pos_type,
        pos_type_upper=pos_type.upper(),
        subtype_list=render_subtype_list(pos_type, include_catch_all=include_catch_all),
    )
    prompt = util.prompt_loader.get_prompt("translation", prompt_type).format(
        word=word, domain=domain, pos_type=pos_type, definition=definition
    )
    offered = [
        value
        for value in get_subtype_values_for_pos(pos_type)
        if include_catch_all or value != _CATCH_ALL_SUBTYPE
    ]
    schema = Schema(
        name="SenseSubtype",
        description="The subtype of one sense's part of speech",
        properties={
            "pos_subtype": SchemaProperty(
                "string", f"The {pos_type} subtype of this sense", enum=offered
            )
        },
    )
    return context, prompt, schema


def query_sense_subtype(
    client: Any,
    word: str,
    definition: str,
    pos_type: str,
    get_session_func: Callable,
    model: Optional[str] = None,
) -> Tuple[Optional[str], bool]:
    """Ask for the subtype of one general-vocabulary sense, catch-all included.

    The second step after ``query_definitions(..., ask_subtype=False)``: one
    call per sense, for a part of speech in :data:`SUBTYPED_POS_TYPES`.

    Returns:
        (the subtype as the enum spells it -- ``other`` for the catch-all --
        or None, success flag)
    """
    context, prompt, schema = build_subtype_prompt(word, definition, pos_type)
    model_name: str = cast(str, model or getattr(client, "model", constants.DEFAULT_MODEL))

    try:
        response = client.generate_chat(
            prompt=prompt, model=model_name, json_schema=schema, context=context
        )
    except Exception as e:
        logger.error(f"Error querying the subtype of '{word}': {type(e).__name__}: {e}")
        return None, False

    session = get_session_func()
    try:
        linguistic_db.log_query(
            session,
            word=word,
            query_type="definitions_subtype",
            prompt=prompt,
            response=json.dumps(response.structured_data),
            model=model_name,
        )
    except Exception as log_err:
        logger.error(f"Failed to log successful query: {log_err}")

    data = response.structured_data
    subtype = data.get("pos_subtype") if isinstance(data, dict) else None
    if not isinstance(subtype, str) or not subtype:
        logger.warning(f"Invalid subtype response for '{word}'")
        return None, False
    return subtype, True
