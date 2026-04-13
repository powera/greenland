#!/usr/bin/python3

"""Barsukas UI language resolution helpers."""

from typing import Optional

from flask import Request

from barsukas.helpers.strings import SUPPORTED_UI_LANGS

UI_LANGUAGE_COOKIE = "barsukas_ui_lang"


def normalize_ui_language(lang: Optional[str]) -> Optional[str]:
    """Return a normalized UI language code if supported."""
    if not lang:
        return None
    normalized = lang.strip().lower()
    if normalized in SUPPORTED_UI_LANGS:
        return normalized
    return None


def resolve_ui_language(request: Request) -> str:
    """Resolve UI language from cookie -> Accept-Language -> English fallback."""
    cookie_lang = normalize_ui_language(request.cookies.get(UI_LANGUAGE_COOKIE))
    if cookie_lang:
        return cookie_lang

    best_header_match = request.accept_languages.best_match(list(SUPPORTED_UI_LANGS))
    header_lang = normalize_ui_language(best_header_match)
    if header_lang:
        return header_lang

    return "en"
