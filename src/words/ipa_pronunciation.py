#!/usr/bin/python3

"""Prompt helpers for word-to-IPA pronunciation tasks."""

from storage.translation_helpers import get_supported_languages


def build_ipa_pronunciation_prompt(
    language_code: str,
    word: str,
    *,
    definition: str = "",
    sentence: str = "",
) -> str:
    """Build a reusable prompt for generating IPA pronunciation of one word."""
    normalized_language = language_code.lower()
    language_names = get_supported_languages()
    language_name = (
        "English"
        if normalized_language == "en"
        else language_names.get(normalized_language, normalized_language)
    )

    context = (
        "You are a linguistics expert specializing in phonetics and IPA transcription. "
        "Return only the IPA pronunciation for the target word with no extra explanation. "
        "Use standard pronunciation for the requested language. "
        "If sentence context is provided, use it to disambiguate pronunciation."
    )

    prompt_lines = [
        "Generate the IPA pronunciation for this word:",
        f"Language: {language_name} ({normalized_language})",
        f"Word: {word}",
    ]

    if definition.strip():
        prompt_lines.append(f"Definition: {definition.strip()}")

    if sentence.strip():
        prompt_lines.append(f"Sentence: {sentence.strip()}")

    prompt_lines.append("Respond with only the IPA transcription.")

    return f"{context}\n\n" + "\n".join(prompt_lines)

