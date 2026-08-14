"""Language and verdict helpers shared by verification services."""

from __future__ import annotations

import logging
from typing import List, Literal, Optional

from storage.translation_helpers import LANGUAGE_NAMES, TIER_1_LANGUAGES

logger = logging.getLogger(__name__)

DEFAULT_VERIFY_LANGUAGES: List[str] = list(TIER_1_LANGUAGES)


def get_supported_languages(model: str) -> List[str]:
    """Return registered language codes accepted by verification prompts.

    Verification uses the configured general-purpose LLM and does not maintain
    a second, model-specific language registry.
    """
    del model
    return list(LANGUAGE_NAMES)


def filter_languages_for_model(requested_languages: List[str], model: str) -> List[str]:
    """Return requested language codes registered for translation storage."""
    supported_languages = get_supported_languages(model)
    filtered_languages = [
        language_code
        for language_code in requested_languages
        if language_code in supported_languages
    ]
    if len(filtered_languages) < len(requested_languages):
        unsupported_languages = set(requested_languages) - set(filtered_languages)
        logger.warning(
            "Verification with model %s skipped unregistered languages %s",
            model,
            sorted(unsupported_languages),
        )
    return filtered_languages


def get_dialect_display_name(language_code: str) -> str:
    """Return the prompt display name for a language code."""
    return str(LANGUAGE_NAMES.get(language_code, language_code))


def parse_verdict(value: Optional[str]) -> Literal["correct", "incorrect"]:
    """Normalize an LLM verdict to ``correct`` or ``incorrect``."""
    if value and value.lower().strip() in {"correct", "true", "yes", "1"}:
        return "correct"
    return "incorrect"
