#!/usr/bin/python3

"""Prompt helpers for synonym generation."""

import json
import logging
from typing import Any, Dict, Optional

from clients.unified_client import UnifiedLLMClient
from langtools.directions import get_language_direction_note
from storage.backend.config import DataSourceConfig
from storage.translation_helpers import get_supported_languages

import util.prompt_loader

logger = logging.getLogger(__name__)

SYNONYMS_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "abbreviations": {"type": "array", "items": {"type": "string"}},
        "expanded_forms": {"type": "array", "items": {"type": "string"}},
        "synonyms": {"type": "array", "items": {"type": "string"}},
        "near_synonyms": {"type": "array", "items": {"type": "string"}},
        "regional_variants": {"type": "array", "items": {"type": "string"}},
        "register_variants": {"type": "array", "items": {"type": "string"}},
        "synecdoche_variants": {"type": "array", "items": {"type": "string"}},
        "related_learner_equivalents": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": [
        "abbreviations",
        "expanded_forms",
        "synonyms",
        "near_synonyms",
        "regional_variants",
        "register_variants",
        "synecdoche_variants",
        "related_learner_equivalents",
    ],
}


def build_synonyms_prompt(
    language_code: str,
    word: str,
    config: DataSourceConfig | None = None,
    *,
    pos_type: str = "noun",
    english_word: str | None = None,
    definition: str = "",
) -> str:
    """Build the shared synonym-generation prompt for a word."""
    _ = config  # reserved for future prompt variations

    normalized_language = language_code.lower()
    language_names = get_supported_languages()
    language_name = (
        "English"
        if normalized_language == "en"
        else language_names.get(normalized_language, normalized_language)
    )

    context = util.prompt_loader.get_context("synonyms", "word")
    prompt_template = util.prompt_loader.get_prompt("synonyms", "word")

    prompt_body = prompt_template.replace("{{language_name}}", language_name)
    prompt_body = prompt_body.replace("{{word}}", word)
    prompt_body = prompt_body.replace("{{pos_type}}", pos_type)
    prompt_body = prompt_body.replace("{{english_word}}", english_word or word)
    prompt_body = prompt_body.replace("{{definition}}", definition)
    prompt_body = prompt_body.replace(
        "{{language_note}}", get_language_direction_note(normalized_language)
    )

    return f"{context}\n\n{prompt_body}"


def query_synonyms(
    language_code: str,
    word: str,
    *,
    client: UnifiedLLMClient,
    model: str,
    config: Optional[DataSourceConfig] = None,
    pos_type: str = "noun",
    english_word: Optional[str] = None,
    definition: str = "",
    json_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the shared synonym prompt against an LLM and return structured data."""
    prompt = build_synonyms_prompt(
        language_code,
        word,
        config=config,
        pos_type=pos_type,
        english_word=english_word,
        definition=definition,
    )

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=json_schema or SYNONYMS_JSON_SCHEMA,
        )
    except Exception as error:
        logger.error("Error querying synonyms for '%s' (%s): %s", word, language_code, error)
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
