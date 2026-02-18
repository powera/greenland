#!/usr/bin/python3

"""Prompt helpers for verb-form generation."""

from storage.backend.config import DataSourceConfig

import util.prompt_loader


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
    prompt = util.prompt_loader.get_prompt("language_forms", prompt_path).format(
        verb=word,
        english_verb=english_word or word,
        definition=definition,
        subtype_context=subtype_context,
    )
    return f"{context}\n\n{prompt}"
