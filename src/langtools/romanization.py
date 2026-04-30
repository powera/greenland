#!/usr/bin/env python3
"""Standardized script-to-Latin romanization helpers.

This module provides one entrypoint (`romanize_text`) for deterministic
romanization used across the codebase. For Chinese/Japanese it delegates to
existing langtools helpers; for Ukrainian it uses a deterministic letter map.
"""

from __future__ import annotations

from typing import Mapping

from langtools.ja.romaji_helper import generate_romaji
from langtools.zh.pinyin_helper import generate_pinyin

_BASIC_UK_ROMANIZATION_MAP: Mapping[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "h",
    "ґ": "g",
    "д": "d",
    "е": "e",
    "є": "ye",
    "ж": "zh",
    "з": "z",
    "и": "y",
    "і": "i",
    "ї": "yi",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ь": "",
    "ю": "yu",
    "я": "ya",
}


def romanize_text(text: str, language_code: str) -> str:
    """Return romanized text when supported; otherwise return input text."""
    normalized_lang = language_code.lower()
    if normalized_lang == "zh":
        return _remove_spaces(generate_pinyin(text)) or text
    if normalized_lang == "ja":
        return _remove_spaces(generate_romaji(text)) or text
    if normalized_lang == "uk":
        return "".join(_BASIC_UK_ROMANIZATION_MAP.get(character, character) for character in text)
    return text


def _remove_spaces(value: str | None) -> str:
    return "" if value is None else value.replace(" ", "")
