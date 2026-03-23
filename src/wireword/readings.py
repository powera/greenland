"""Helpers for manifest-driven WireWord reading metadata."""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from langtools.ja.romaji_helper import generate_hiragana, generate_romaji
from langtools.zh.pinyin_helper import generate_pinyin

ReadingGenerator = Callable[[str], Optional[str]]

READING_LABELS: dict[str, str] = {
    "pinyin": "Pinyin",
    "romaji": "Romaji",
    "hiragana": "Hiragana",
}

READING_GENERATORS_BY_LANGUAGE: dict[str, dict[str, ReadingGenerator]] = {
    "zh": {
        "pinyin": generate_pinyin,
    },
    "ja": {
        "romaji": generate_romaji,
        "hiragana": generate_hiragana,
    },
}

DEFAULT_READING_SYSTEM_BY_LANGUAGE: dict[str, str] = {
    "zh": "pinyin",
    "ja": "hiragana",
}


def get_manifest_reading_config(language_code: str) -> Optional[dict[str, Any]]:
    """Return manifest reading configuration for a target language."""
    generators = READING_GENERATORS_BY_LANGUAGE.get(language_code)
    if not generators:
        return None

    systems: list[dict[str, str]] = []
    for system_id in generators:
        systems.append(
            {
                "id": system_id,
                "label": READING_LABELS[system_id],
                "word_field": f"target_{system_id}",
                "grammatical_form_field": f"target_{system_id}",
                "alternatives_field": f"target_alternatives_{system_id}",
                "synonyms_field": f"target_synonyms_{system_id}",
                "sentence_translation_field": system_id,
            }
        )

    return {
        "style": "ruby",
        "default_system": DEFAULT_READING_SYSTEM_BY_LANGUAGE[language_code],
        "systems": systems,
    }


def build_target_reading_fields(language_code: str, target_text: Optional[str]) -> dict[str, str]:
    """Build word-level or grammatical-form reading fields for a target string."""
    if not target_text:
        return {}

    generators = READING_GENERATORS_BY_LANGUAGE.get(language_code)
    if not generators:
        return {}

    reading_fields: dict[str, str] = {}
    for system_id, generator in generators.items():
        reading_value = generator(target_text)
        if reading_value:
            reading_fields[f"target_{system_id}"] = reading_value

    return reading_fields


def build_target_reading_list_fields(
    language_code: str,
    target_texts: Sequence[str],
    base_field_name: str,
) -> dict[str, list[str]]:
    """Build parallel reading arrays for alternative or synonym target strings."""
    generators = READING_GENERATORS_BY_LANGUAGE.get(language_code)
    if not generators or not target_texts:
        return {}

    reading_lists: dict[str, list[str]] = {system_id: [] for system_id in generators}
    has_non_empty_values: dict[str, bool] = {system_id: False for system_id in generators}

    for target_text in target_texts:
        for system_id, generator in generators.items():
            reading_value = generator(target_text) or ""
            reading_lists[system_id].append(reading_value)
            if reading_value:
                has_non_empty_values[system_id] = True

    return {
        f"{base_field_name}_{system_id}": reading_lists[system_id]
        for system_id in generators
        if has_non_empty_values[system_id]
    }


def build_translation_reading_fields(
    language_code: str, target_text: Optional[str]
) -> dict[str, str]:
    """Build translation-dict reading fields for sentences or conversations."""
    if not target_text:
        return {}

    generators = READING_GENERATORS_BY_LANGUAGE.get(language_code)
    if not generators:
        return {}

    reading_fields: dict[str, str] = {}
    for system_id, generator in generators.items():
        reading_value = generator(target_text)
        if reading_value:
            reading_fields[system_id] = reading_value

    return reading_fields
