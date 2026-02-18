#!/usr/bin/python3

"""Prompt helpers for synonym generation."""

from storage.backend.config import DataSourceConfig
from storage.translation_helpers import get_supported_languages

import util.prompt_loader


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

    language_note = ""
    if normalized_language == "ko":
        language_note = "- For Korean, provide words in Hangul (e.g., 거리, 길 for 'street')"

    prompt_body = prompt_template.replace("{{language_name}}", language_name)
    prompt_body = prompt_body.replace("{{word}}", word)
    prompt_body = prompt_body.replace("{{pos_type}}", pos_type)
    prompt_body = prompt_body.replace("{{english_word}}", english_word or word)
    prompt_body = prompt_body.replace("{{definition}}", definition)
    prompt_body = prompt_body.replace("{{language_note}}", language_note)

    return f"{context}\n\n{prompt_body}"
