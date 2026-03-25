#!/usr/bin/python3

"""Prompt helpers for word-to-IPA pronunciation tasks."""

import json
import logging
from typing import Any, Dict, Optional

from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.translation_helpers import get_supported_languages

import util.prompt_loader

logger = logging.getLogger(__name__)

IPA_PRONUNCIATION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ipa": {
            "type": "string",
            "description": "IPA pronunciation of the provided word in the requested language",
        }
    },
    "required": ["ipa"],
}


def build_ipa_pronunciation_prompt(
    language_code: str,
    word: str,
    config: DataSourceConfig | None = None,
    *,
    definition: str = "",
    sentence: str = "",
    grammatical_form: str = "",
) -> str:
    """Build a reusable prompt for generating IPA pronunciation of one word."""
    _ = config  # reserved for future prompt variations

    normalized_language = language_code.lower()
    language_names = get_supported_languages()
    language_name = (
        "English"
        if normalized_language == "en"
        else language_names.get(normalized_language, normalized_language)
    )

    context = util.prompt_loader.get_context("pronunciation", "ipa")
    prompt_template = util.prompt_loader.get_prompt("pronunciation", "ipa")

    grammatical_form_line = (
        f"Grammatical form: {grammatical_form.strip()}\n" if grammatical_form.strip() else ""
    )
    definition_line = f"Definition: {definition.strip()}\n" if definition.strip() else ""
    sentence_line = f"Sentence: {sentence.strip()}\n" if sentence.strip() else ""

    prompt = prompt_template.format(
        language_name=language_name,
        language_code=normalized_language,
        word=word,
        grammatical_form_line=grammatical_form_line,
        definition_line=definition_line,
        sentence_line=sentence_line,
    )

    return f"{context}\n\n{prompt}"


def generate_ipa_pronunciation(
    language_code: str,
    word: str,
    *,
    client: UnifiedLLMClient,
    model: str,
    config: Optional[DataSourceConfig] = None,
    definition: str = "",
    sentence: str = "",
    grammatical_form: str = "",
    json_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the shared IPA prompt against an LLM and return structured data."""
    combined_prompt = build_ipa_pronunciation_prompt(
        language_code,
        word,
        config=config,
        definition=definition,
        sentence=sentence,
        grammatical_form=grammatical_form,
    )
    context, prompt = combined_prompt.split("\n\n", 1)

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=json_schema or IPA_PRONUNCIATION_JSON_SCHEMA,
            context=context,
        )
    except Exception as error:
        logger.error(
            "Error querying IPA pronunciation for '%s' (%s): %s", word, language_code, error
        )
        return {"success": False, "error": str(error)}

    if not response.structured_data:
        return {"success": False, "error": "Empty response from LLM"}

    result = response.structured_data
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError as error:
            return {"success": False, "error": f"Invalid JSON response: {error}"}

    if not isinstance(result, dict):
        return {"success": False, "error": "Structured response is not an object"}

    merged: Dict[str, Any] = {"success": True}
    merged.update(result)
    return merged


def query_ipa_pronunciation(
    language_code: str,
    word: str,
    *,
    client: UnifiedLLMClient,
    model: str,
    config: Optional[DataSourceConfig] = None,
    definition: str = "",
    sentence: str = "",
    grammatical_form: str = "",
    json_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Backward-compatible wrapper for IPA generation calls."""
    return generate_ipa_pronunciation(
        language_code=language_code,
        word=word,
        client=client,
        model=model,
        config=config,
        definition=definition,
        sentence=sentence,
        grammatical_form=grammatical_form,
        json_schema=json_schema,
    )
