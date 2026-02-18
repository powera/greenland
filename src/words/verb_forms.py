#!/usr/bin/python3

"""Prompt helpers for verb-form generation."""

import json
import logging
from typing import Any, Dict, Optional

from clients.types import Schema
from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig

import util.prompt_loader
from langtools.verb_forms import get_language_verb_forms_config

logger = logging.getLogger(__name__)


def build_verb_forms_prompt(
    language_code: str,
    word: str,
    config: DataSourceConfig | None = None,
    *,
    english_word: str | None = None,
    definition: str = "",
    subtype_context: str = "",
) -> str:
    """Build the shared verb-form prompt for one language/word pair."""
    _ = config  # reserved for future prompt variations

    prompt_path = f"{language_code.lower()}/verb"
    context = util.prompt_loader.get_context("language_forms", prompt_path)
    language_config = get_language_verb_forms_config(language_code)
    prompt_note = language_config.get("prompt_note", "")

    prompt = util.prompt_loader.get_prompt("language_forms", prompt_path).format(
        verb=word,
        english_verb=english_word or word,
        definition=definition,
        subtype_context=subtype_context,
    )

    if isinstance(prompt_note, str) and prompt_note.strip():
        prompt = f"{prompt}\n\nAdditional language-specific guidance:\n{prompt_note.strip()}"

    return f"{context}\n\n{prompt}"


def query_verb_forms(
    language_code: str,
    word: str,
    *,
    client: UnifiedLLMClient,
    model: str,
    json_schema: Dict[str, Any] | Schema,
    config: Optional[DataSourceConfig] = None,
    english_word: Optional[str] = None,
    definition: str = "",
    subtype_context: str = "",
) -> Dict[str, Any]:
    """Run the shared verb-form prompt against an LLM and return structured data."""
    combined_prompt = build_verb_forms_prompt(
        language_code,
        word,
        config=config,
        english_word=english_word,
        definition=definition,
        subtype_context=subtype_context,
    )
    context, prompt = combined_prompt.split("\n\n", 1)

    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=json_schema,
            context=context,
        )
    except Exception as error:
        logger.error("Error querying verb forms for '%s' (%s): %s", word, language_code, error)
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
