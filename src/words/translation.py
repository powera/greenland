#!/usr/bin/python3

"""Prompt helpers and LLM query wrappers for single-word translation tasks."""

import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from clients.unified_client import UnifiedLLMClient
from storage.backend.config import DataSourceConfig
from storage.translation_helpers import get_supported_languages

import util.prompt_loader

logger = logging.getLogger(__name__)
_DEFAULT_TRANSLATION_MODEL = "gpt-5-mini"


def _language_name(language_code: str) -> str:
    """Resolve a language code into a display name."""
    language_names = get_supported_languages()
    return language_names.get(language_code.lower(), language_code.upper())


def _resolve_model(config: DataSourceConfig, model: Optional[str] = None) -> str:
    """Resolve the model to use from explicit override, then config, then default."""
    return model or config.model or _DEFAULT_TRANSLATION_MODEL


def build_single_target_translation_prompt(
    source_word: str,
    source_language: str,
    target_language: str,
    candidate_translations: Sequence[str] | None = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """Build context, prompt, and response schema for one target-language translation."""
    context = util.prompt_loader.get_context("translation", "word")

    prompt_lines = [
        f'Translate the single word "{source_word}" from {_language_name(source_language)} to {_language_name(target_language)}.',
        "Return only one translation in lemma/base form.",
    ]

    if candidate_translations:
        candidates = "\n".join(f"- {candidate}" for candidate in candidate_translations)
        prompt_lines.extend(
            [
                "For benchmark scoring, choose exactly one candidate as the translation.",
                "Candidate translations:",
                candidates,
            ]
        )

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "translation": {
                "type": "string",
                "description": f"Single-word translation into {_language_name(target_language)}",
            }
        },
        "required": ["translation"],
    }

    return context, "\n".join(prompt_lines), schema


def build_multi_target_translation_prompt(
    source_word: str,
    source_language: str,
    target_languages: Sequence[str],
) -> Tuple[str, str, Dict[str, Any]]:
    """Build context, prompt, and response schema for many target-language translations."""
    normalized_targets: List[str] = [language.lower() for language in target_languages]
    context = util.prompt_loader.get_context("translation", "word")

    target_lines = "\n".join(
        f"- {code}: {_language_name(code)}" for code in normalized_targets
    )
    prompt = (
        f'Translate the single word "{source_word}" from {_language_name(source_language)} into each requested target language.\n'
        "Return lemma/base-form translations only.\n"
        "Target languages:\n"
        f"{target_lines}"
    )

    schema_properties = {
        language: {
            "type": "string",
            "description": f"Single-word translation into {_language_name(language)}",
        }
        for language in normalized_targets
    }
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": schema_properties,
        "required": list(schema_properties.keys()),
    }

    return context, prompt, schema


def query_single_word_translation(
    source_word: str,
    source_language: str,
    target_language: str,
    *,
    config: DataSourceConfig,
    client: Optional[UnifiedLLMClient] = None,
    model: Optional[str] = None,
    candidate_translations: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Query the LLM for a single-target word translation."""
    translation_client = client or UnifiedLLMClient.from_config(config)
    resolved_model = _resolve_model(config, model)
    context, prompt, schema = build_single_target_translation_prompt(
        source_word=source_word,
        source_language=source_language,
        target_language=target_language,
        candidate_translations=candidate_translations,
    )

    try:
        response = translation_client.generate_chat(
            prompt=prompt,
            model=resolved_model,
            json_schema=schema,
            context=context,
        )
    except Exception as error:
        logger.error(
            "Error translating word '%s' (%s -> %s): %s",
            source_word,
            source_language,
            target_language,
            error,
        )
        return {"success": False, "error": str(error)}

    structured_data = response.structured_data
    if isinstance(structured_data, str):
        try:
            structured_data = json.loads(structured_data)
        except json.JSONDecodeError as error:
            return {"success": False, "error": f"Invalid JSON response: {error}"}

    if not isinstance(structured_data, dict):
        return {"success": False, "error": "Structured response is not an object"}

    translation = structured_data.get("translation")
    if not isinstance(translation, str) or not translation.strip():
        return {"success": False, "error": "Missing translation in response"}

    return {"success": True, "translation": translation.strip()}


def query_multi_word_translation(
    source_word: str,
    source_language: str,
    target_languages: Sequence[str],
    *,
    config: DataSourceConfig,
    client: Optional[UnifiedLLMClient] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Query the LLM for multi-target word translations."""
    normalized_targets = [language.lower() for language in target_languages]
    if not normalized_targets:
        return {"success": False, "error": "target_languages must not be empty"}

    translation_client = client or UnifiedLLMClient.from_config(config)
    resolved_model = _resolve_model(config, model)
    context, prompt, schema = build_multi_target_translation_prompt(
        source_word=source_word,
        source_language=source_language,
        target_languages=normalized_targets,
    )

    try:
        response = translation_client.generate_chat(
            prompt=prompt,
            model=resolved_model,
            json_schema=schema,
            context=context,
        )
    except Exception as error:
        logger.error(
            "Error translating word '%s' (%s -> %s): %s",
            source_word,
            source_language,
            ",".join(normalized_targets),
            error,
        )
        return {"success": False, "error": str(error)}

    structured_data = response.structured_data
    if isinstance(structured_data, str):
        try:
            structured_data = json.loads(structured_data)
        except json.JSONDecodeError as error:
            return {"success": False, "error": f"Invalid JSON response: {error}"}

    if not isinstance(structured_data, dict):
        return {"success": False, "error": "Structured response is not an object"}

    result: Dict[str, Any] = {"success": True}
    for language in normalized_targets:
        value = structured_data.get(language)
        if not isinstance(value, str) or not value.strip():
            return {
                "success": False,
                "error": f"Missing translation for target language '{language}'",
            }
        result[language] = value.strip()

    return result
