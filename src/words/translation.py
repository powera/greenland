#!/usr/bin/python3

"""Prompt helpers for single-word translation tasks."""

from typing import Any, Dict, List, Sequence, Tuple

from storage.translation_helpers import get_supported_languages

import util.prompt_loader


def _language_name(language_code: str) -> str:
    """Resolve a language code into a display name."""
    language_names = get_supported_languages()
    return language_names.get(language_code.lower(), language_code.upper())


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
