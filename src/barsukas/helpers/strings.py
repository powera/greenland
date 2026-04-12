#!/usr/bin/python3

"""Helpers for loading Barsukas UI strings from namespaced JSON files."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, cast

SUPPORTED_UI_LANGS = frozenset({"en", "lt"})
_STRINGS_ROOT = Path(__file__).resolve().parents[3] / "strings" / "barsukas"


@lru_cache(maxsize=64)
def _load_namespace_file(namespace: str, ui_lang: str) -> Dict[str, Any]:
    """Load one namespace JSON file with English fallback."""
    if ui_lang not in SUPPORTED_UI_LANGS:
        ui_lang = "en"

    namespace_path = _STRINGS_ROOT / namespace / f"{ui_lang}.json"
    fallback_path = _STRINGS_ROOT / namespace / "en.json"

    if namespace_path.exists():
        with namespace_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
            return cast(Dict[str, Any], loaded)

    if fallback_path.exists():
        with fallback_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
            return cast(Dict[str, Any], loaded)

    return {}


def load_barsukas_strings(namespace: str, ui_lang: str) -> Dict[str, Any]:
    """Public helper for route handlers to fetch namespace strings."""
    return _load_namespace_file(namespace=namespace, ui_lang=ui_lang)
