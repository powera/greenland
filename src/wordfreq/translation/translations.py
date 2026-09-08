#!/usr/bin/python3

"""Translation queries for linguistic analysis."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import util.prompt_loader
from clients.types import Schema, SchemaProperty
from storage import database as linguistic_db
from storage.translation_helpers import (
    ANCIENT_LANGUAGE_GROUP,
    MAX_LLM_LANGUAGES_PER_OPERATION,
    LANGUAGE_NAMES,
    TRANSLATION_STATUS_VALUES,
)
from wordfreq.translation.constants import (
    AVAILABLE_TRANSLATION_LANGUAGES,
    AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE,
)

logger = logging.getLogger(__name__)


# Requirements 7-8 of the word-translation context, added only when an ancient
# language is among the targets.  ``translation_status`` exists for that group,
# where how a concept is rendered is itself the evidence words.term_age reads;
# for a living language a bare "conventional" is the assumed default and is
# discarded on the way into storage (see
# storage.translation_helpers.translation_status_is_informative).  Asking for it
# anyway spent a third of the context on a taxonomy that could not fire, and
# invited the model to mark ordinary loanwords in living languages.
ANCIENT_STATUS_REQUIREMENTS = """7. For each translation, classify its historical/native fit:
   - conventional: ordinary native or historically established vocabulary for the target language
   - late_construction: a useful learner cue, but a Neo-Latin, post-classical, modern Sanskrit coinage, post-1200 Classical Arabic construction, or otherwise late learned construction
   - modern_loan: a modern loanword or transliteration rather than native/classical vocabulary
   - descriptive: a descriptive phrase/compound used because there is no simple ordinary term
   - modern_reimagining: a genuinely ancient word reapplied to a modern concept, so its attestation says nothing about the concept's age - Sanskrit विमानम् for "airplane" names a flying palace in the epics. Attestation only in myth or literature is not conventional usage
   - uncertain: use only when the fit is genuinely unclear
8. For the ancient/classical target language group (Latin, Sanskrit, Ancient Greek, Classical Arabic pre-1200, and Old Norse), expect lexical gaps and do not hide modernity: mark post-classical foods, institutions, clothing, technologies, and modern loans clearly.
"""

ANCIENT_STATUS_NOTE_INSTRUCTION = " Return an empty status note for conventional translations; otherwise briefly explain the marker."


def _requests_ancient_language(languages: List[str]) -> bool:
    """Whether any target language is scored on translation_status.

    The ancient group has no dialects, so a direct membership test is exact -
    matching the reasoning in ``translation_status_is_informative``.
    """
    return any(lang_code in ANCIENT_LANGUAGE_GROUP for lang_code in languages)


def query_translations(
    client: Any,
    english_word: str,
    reference_translation: Tuple[str, str],
    definition: str,
    pos_type: str,
    get_session_func: Callable,
    pos_subtype: Optional[str] = None,
    languages: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Query LLM to generate translations for a word with known English, reference translation, and definition.

    This is used when you already have the English lemma, one reference translation, and definition
    in the database, and you just need to generate translations to other languages.

    Args:
        client: UnifiedLLMClient instance
        english_word: English lemma form
        reference_translation: Tuple of (language_code, translation) for a known translation in another language
                              e.g., ('lt', 'valgyti') or ('fr', 'manger'). Used as context for generating other translations.
        definition: Definition of the word
        pos_type: Part of speech (noun, verb, etc.)
        get_session_func: Function to get database session
        pos_subtype: Optional part of speech subtype
        languages: List of ISO language codes to translate to (e.g., ['fr', 'es', 'de']).
                  If None, uses default set: ['zh', 'ko', 'fr', 'es', 'de', 'pt', 'sw', 'vi']

    Returns:
        Tuple of (translations dict, success flag)
        translations dict has keys like: chinese_translation, french_translation, spanish_translation, etc.
    """
    if not english_word or not reference_translation or len(reference_translation) != 2:
        logger.error("English word and reference translation (lang_code, translation) are required")
        return {}, False

    ref_lang_code, ref_translation = reference_translation
    if not ref_lang_code or not ref_translation:
        logger.error("Reference translation must contain both language code and translation text")
        return {}, False

    # Use default languages if not specified
    if languages is None:
        languages = ["zh", "ko", "fr", "es", "de", "pt", "sw", "vi"]

    if len(languages) > MAX_LLM_LANGUAGES_PER_OPERATION:
        logger.warning(
            "Translation generation requested %s languages; limiting to first %s",
            len(languages),
            MAX_LLM_LANGUAGES_PER_OPERATION,
        )
        languages = languages[:MAX_LLM_LANGUAGES_PER_OPERATION]

    # Build schema properties dynamically based on requested languages
    schema_properties = {}
    languages_list_lines = []
    language_instructions_lines = []

    # Only the ancient group is scored on translation_status, so only ask for it
    # when one is present.  For a living language the answer is "conventional"
    # for nearly every word and is dropped before storage anyway.
    include_status = _requests_ancient_language(languages)

    for lang_code in languages:
        lang_config = AVAILABLE_TRANSLATION_LANGUAGES_BY_CODE.get(lang_code)
        if lang_config is None:
            logger.warning(f"Unknown language code '{lang_code}' requested, skipping")
            continue
        language_properties = {
            "translation": SchemaProperty("string", lang_config["description"]),
        }
        if include_status:
            language_properties["translation_status"] = SchemaProperty(
                "string",
                "How historically native the translation is: conventional, late_construction, modern_loan, descriptive, modern_reimagining, or uncertain. "
                "'conventional' is the default and is discarded for modern languages, so it only ever matters that you mark the others.",
                enum=sorted(TRANSLATION_STATUS_VALUES),
            )
            language_properties["translation_status_note"] = SchemaProperty(
                "string",
                "Brief note when status is not conventional; otherwise an empty string.",
            )
        schema_properties[lang_config["field"]] = SchemaProperty(
            "object",
            lang_config["description"],
            properties=language_properties,
        )
        # Use the canonical language name (without script qualifier) for the prompt bullet list
        display_name = LANGUAGE_NAMES.get(lang_code, lang_code)
        languages_list_lines.append(f"- {display_name}")
        language_instructions_lines.append(lang_config["instructions"])

    if not schema_properties:
        logger.error("No valid languages specified")
        return {}, False

    schema = Schema(
        name="Translations",
        description="Translations for a word to multiple languages",
        properties=schema_properties,
    )

    context_template = util.prompt_loader.get_context("translation", "word")
    prompt_template = util.prompt_loader.get_prompt("translation", "word")

    subtype_info = f"Subtype: {pos_subtype}" if pos_subtype else ""
    languages_list = "\n".join(languages_list_lines)
    language_instructions = "\n".join(language_instructions_lines)

    # Map language code to full language name (imported from translation_helpers)
    reference_language_name = LANGUAGE_NAMES.get(ref_lang_code, ref_lang_code.capitalize())

    # Format context with language instructions, adding the status taxonomy
    # only for a batch that contains a language scored on it.
    context = context_template.format(
        language_instructions=language_instructions,
        status_requirements=ANCIENT_STATUS_REQUIREMENTS if include_status else "",
        status_note_instruction=ANCIENT_STATUS_NOTE_INSTRUCTION if include_status else "",
    )

    # Conditionally format reference info and disambiguation instruction
    # If reference language is English, we don't have a true reference translation
    if ref_lang_code != "en":
        reference_info = f'{reference_language_name}: "{ref_translation}" (lemma form)\n'
        disambiguation_instruction = f"Ensure all translations match the specific meaning indicated by the English and {reference_language_name} translations."
    else:
        # No reference translation - rely on definition and POS
        reference_info = ""
        disambiguation_instruction = "Ensure all translations match the specific meaning indicated by the definition and part of speech."

    prompt = prompt_template.format(
        english_word=english_word,
        reference_info=reference_info,
        definition=definition,
        pos_type=pos_type,
        subtype_info=subtype_info,
        languages_list=languages_list,
        disambiguation_instruction=disambiguation_instruction,
    )

    try:
        response = client.generate_chat(
            prompt=prompt, model=model, json_schema=schema, context=context
        )
        setattr(
            client, "_last_query_cost_usd", float(response.usage.cost) if response.usage else 0.0
        )

        # Log successful query
        session = get_session_func()
        try:
            linguistic_db.log_query(
                session,
                word=english_word,
                query_type="translation_generation",
                prompt=prompt,
                response=json.dumps(response.structured_data),
                model=model or "unknown",
            )
        except Exception as log_err:
            logger.error(f"Failed to log successful query: {log_err}")

        # Validate and return response data
        if response.structured_data and isinstance(response.structured_data, dict):
            return response.structured_data, True
        else:
            logger.warning(f"Invalid response format for word '{english_word}'")
            return {}, False

    except Exception as e:
        setattr(client, "_last_query_cost_usd", 0.0)
        logger.error(f"Error generating translations for '{english_word}': {type(e).__name__}: {e}")
        return {}, False
